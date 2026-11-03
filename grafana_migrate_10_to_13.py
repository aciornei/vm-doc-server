#!/usr/bin/env python3
"""Migrate Grafana 10 dashboards and folders to Grafana 13.

Read-only by default. Uses legacy /api endpoints, still supported in Grafana 13.
Requires: pip install requests
Environment: GRAFANA_OLD_URL, GRAFANA_OLD_TOKEN,
             GRAFANA_NEW_URL, GRAFANA_NEW_TOKEN

Supports: paginated discovery, folder hierarchy/UIDs, dashboard UIDs,
          datasource UID remapping by source/target name+type, local JSON backup.
Does NOT migrate: unified alerts, permissions, library panels, dashboard history,
                 playlists, plugins, users, or datasource definitions.
"""

import argparse
import copy
import datetime as dt
import json
import os
import pathlib
import sys
from urllib.parse import quote

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: python3 -m pip install requests")


class MigrationError(Exception):
    pass


class Grafana:
    def __init__(self, url, token, verify=True, timeout=25):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self.verify = verify
        self.timeout = timeout

    def request(self, method, path, *, params=None, payload=None, not_found_ok=False):
        url = self.url + path
        try:
            resp = self.session.request(
                method, url, params=params, json=payload,
                verify=self.verify, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise MigrationError(f"{method} {path}: network/TLS error: {exc}") from exc
        if resp.status_code == 404 and not_found_ok:
            return None
        if resp.status_code < 200 or resp.status_code >= 300:
            detail = resp.text.replace("\n", " ")[:600]
            raise MigrationError(f"{method} {path}: HTTP {resp.status_code}: {detail}")
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            raise MigrationError(f"{method} {path}: non-JSON API response") from exc

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, payload):
        return self.request("POST", path, payload=payload)

    def search(self, item_type):
        found = {}
        for page in range(1, 1001):
            batch = self.get("/api/search", params={
                "type": item_type, "limit": 5000, "page": page,
            })
            if not isinstance(batch, list):
                raise MigrationError("/api/search returned a non-list response")
            for item in batch:
                if item.get("uid"):
                    found[item["uid"]] = item
            if len(batch) < 5000:
                return list(found.values())
        raise MigrationError("/api/search exceeded 1000 pages; aborting")

    def folder(self, uid):
        return self.get(f"/api/folders/{quote(uid, safe='')}", not_found_ok=True)

    def dashboard(self, uid):
        return self.get(f"/api/dashboards/uid/{quote(uid, safe='')}", not_found_ok=True)

    def datasources(self):
        data = self.get("/api/datasources")
        if not isinstance(data, list):
            raise MigrationError("/api/datasources returned a non-list response")
        return data


def folder_order(folders):
    by_uid = {item["uid"]: item for item in folders}
    result, marked = [], {}

    def visit(uid):
        state = marked.get(uid, 0)
        if state == 1:
            raise MigrationError(f"Circular parent relation in folders at {uid}")
        if state == 2:
            return
        marked[uid] = 1
        parent = by_uid[uid].get("parentUid") or ""
        if parent:
            if parent not in by_uid:
                raise MigrationError(f"Folder {uid} has missing/inaccessible parent {parent}")
            visit(parent)
        marked[uid] = 2
        result.append(by_uid[uid])

    for uid in by_uid:
        visit(uid)
    return result


def mapping_by_source_uid(src, dest):
    """Match datasource by exact (name, type), not by numeric ID."""
    dest_idx = {}
    for obj in dest:
        dest_idx.setdefault((obj.get("name"), obj.get("type")), []).append(obj)
    out, issues = {}, []
    for old in src:
        name, kind, uid = old.get("name"), old.get("type"), old.get("uid")
        if not uid:
            issues.append(f"Source datasource {name!r} has no UID")
            continue
        matches = dest_idx.get((name, kind), [])
        if len(matches) == 1 and matches[0].get("uid"):
            out[uid] = {"uid": matches[0]["uid"], "type": kind, "name": name}
        else:
            issues.append(f"Datasource missing/ambiguous on destination: {name} ({kind}) [old UID={uid}]")
    return out, issues


def remap_datasources(dashboard, ds_map, src_sources):
    """Copy and replace only explicit datasource references, never dashboard/panel UIDs."""
    data = copy.deepcopy(dashboard)
    warnings = set()
    source_by_uid = {d.get("uid"): d for d in src_sources if d.get("uid")}
    source_by_name = {d.get("name"): d for d in src_sources if d.get("name")}
    reserved = {"-- Grafana --", "-- Mixed --", "grafana", "__expr__", "__dashboard__"}

    def replace_uid(value, loc):
        if not isinstance(value, str) or not value or value in reserved:
            return value
        if value.startswith(("$", "${")):
            return value  # datasource is selected using a Grafana template variable
        old = source_by_uid.get(value)
        if old:
            if value in ds_map:
                return ds_map[value]["uid"]
            warnings.add(f"{loc}: datasource {old.get('name')!r} has no destination match")
        return value

    def replace_datasource(value, loc):
        if isinstance(value, str):
            if value in source_by_name:
                old = source_by_name[value]
                if old.get("uid") not in ds_map:
                    warnings.add(f"{loc}: datasource {value!r} missing on destination")
                return value  # same name is used in the target
            return replace_uid(value, loc)
        if isinstance(value, dict):
            # Datasource ref objects also occur within panel targets and annotations.
            uid = value.get("uid")
            if isinstance(uid, str):
                new_uid = replace_uid(uid, loc)
                if new_uid != uid:
                    value["uid"] = new_uid
                    value["type"] = ds_map[uid]["type"]
            return value
        return value

    def walk(node, path="dashboard"):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "datasource":
                    node[key] = replace_datasource(value, path + ".datasource")
                elif key in {"datasourceUid", "datasource_uid"}:
                    node[key] = replace_uid(value, path + "." + key)
                else:
                    walk(value, path + "." + key)
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, path + f"[{idx}]")

    walk(data)
    # Grafana datasource template-variable selections may contain source UIDs.
    for var in data.get("templating", {}).get("list", []):
        if var.get("type") != "datasource":
            continue
        current = var.get("current")
        if isinstance(current, dict):
            val = current.get("value")
            if isinstance(val, str):
                current["value"] = replace_uid(val, f"templating.{var.get('name')}.current")
            elif isinstance(val, list):
                current["value"] = [replace_uid(v, f"templating.{var.get('name')}.current") for v in val]
        for option in var.get("options") or []:
            if isinstance(option, dict) and isinstance(option.get("value"), str):
                option["value"] = replace_uid(option["value"], f"templating.{var.get('name')}.options")
    return data, sorted(warnings)


def inspect_limitations(data):
    notices = set()

    def walk(node):
        if isinstance(node, dict):
            if "libraryPanel" in node:
                notices.add("Uses a library panel (library elements are NOT migrated)")
            if "alert" in node:
                notices.add("Contains legacy panel alert configuration (review in Grafana 13)")
            if "__inputs" in node:
                notices.add("Contains __inputs datasource placeholders (review manually)")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return sorted(notices)


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8") as fh:
        json.dump(value, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create missing folders/dashboards")
    parser.add_argument("--overwrite", action="store_true", help="With --apply, explicitly update existing dashboards")
    parser.add_argument("--allow-unmatched-datasources", action="store_true",
                        help="Allow import even if some datasource references cannot be mapped")
    parser.add_argument("--backup-dir", default=None, help="Directory for JSON exports")
    parser.add_argument("--ca-bundle", default=None, help="Custom CA bundle path for TLS verification")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification (NOT recommended)")
    args = parser.parse_args()

    if args.overwrite and not args.apply:
        parser.error("--overwrite requires --apply")
    if args.ca_bundle and args.insecure:
        parser.error("Choose either --ca-bundle or --insecure")

    env_keys = ["GRAFANA_OLD_URL", "GRAFANA_OLD_TOKEN", "GRAFANA_NEW_URL", "GRAFANA_NEW_TOKEN"]
    missing = [key for key in env_keys if not os.environ.get(key)]
    if missing:
        parser.error("Missing environment variables: " + ", ".join(missing))
    old_url = os.environ["GRAFANA_OLD_URL"].rstrip("/")
    new_url = os.environ["GRAFANA_NEW_URL"].rstrip("/")
    if old_url == new_url:
        parser.error("Old URL and new URL are identical; aborting")
    if not old_url.startswith(("https://", "http://")) or not new_url.startswith(("https://", "http://")):
        parser.error("Both URLs must begin with http:// or https://")

    verify = False if args.insecure else (args.ca_bundle if args.ca_bundle else True)
    if args.insecure:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    os.umask(0o077)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = pathlib.Path(args.backup_dir or ("grafana_backup_" + timestamp))
    old = Grafana(old_url, os.environ["GRAFANA_OLD_TOKEN"], verify=verify)
    new = Grafana(new_url, os.environ["GRAFANA_NEW_TOKEN"], verify=verify)

    for label, client in [("OLD", old), ("NEW", new)]:
        health = client.get("/api/health")
        print(f"{label}: {client.url} | version={health.get('version', 'unknown')}")

    old_folders_basic = old.search("dash-folder")
    old_dashboards = old.search("dash-db")
    old_folders = []
    for f in old_folders_basic:
        detail = old.folder(f["uid"])
        if detail is None:
            raise MigrationError(f"Source folder disappeared: {f['uid']}")
        old_folders.append({"uid": f["uid"], "title": detail["title"],
                            "parentUid": detail.get("parentUid") or ""})
    old_folders = folder_order(old_folders)
    old_ds = old.datasources()
    new_ds = new.datasources()
    ds_map, ds_issues = mapping_by_source_uid(old_ds, new_ds)

    if args.apply:
        # Safety: don't begin writing until every dashboard has been read/backed up.
        pass
    save_json(backup_dir / "folders.json", old_folders)
    save_json(backup_dir / "datasources_summary.json", {
        "old": [{k: d.get(k) for k in ("uid", "name", "type")} for d in old_ds],
        "new": [{k: d.get(k) for k in ("uid", "name", "type")} for d in new_ds],
        "mapping": ds_map, "unmatched": ds_issues,
    })

    records = []
    for item in old_dashboards:
        uid = item["uid"]
        exported = old.dashboard(uid)
        if exported is None or not isinstance(exported.get("dashboard"), dict):
            raise MigrationError(f"Could not export dashboard {uid}")
        save_json(backup_dir / "original" / (uid + ".json"), exported)
        dash = exported["dashboard"]
        prepared, warnings = remap_datasources(dash, ds_map, old_ds)
        warnings += inspect_limitations(prepared)
        # Removing source DB ID/version is essential: these are instance-local.
        prepared["id"] = None
        prepared["version"] = 0
        prepared["uid"] = uid
        folder_uid = exported.get("meta", {}).get("folderUid") or item.get("folderUid") or ""
        save_json(backup_dir / "prepared" / (uid + ".json"), {
            "dashboard": prepared, "folderUid": folder_uid,
            "overwrite": False, "message": "Migration from Grafana 10",
        })
        records.append({"uid": uid, "title": dash.get("title", item.get("title", "?")),
                        "folderUid": folder_uid, "dashboard": prepared,
                        "warnings": sorted(set(warnings))})

    folder_uids = {f["uid"] for f in old_folders}
    for record in records:
        if record["folderUid"] and record["folderUid"] not in folder_uids:
            record["warnings"].append(
                f"Folder {record['folderUid']} not present in source folder list")

    print(f"\nFound {len(old_folders)} folders, {len(records)} dashboards")
    print(f"Datasource matched: {len(ds_map)}/{len(old_ds)}")
    for issue in ds_issues:
        print("  DS WARNING:", issue)
    for record in records:
        print(f" - {record['title']} [{record['uid']}] folder={record['folderUid'] or 'General'}")
        for issue in record["warnings"]:
            print("    WARNING:", issue)
    print("Backup JSON:", backup_dir.resolve())

    if not args.apply:
        print("\nDRY RUN: destination inventory (read-only)")
        planned_folders = planned_dashboards = existing_dashboards = conflicts = 0
        for folder in old_folders:
            existing = new.folder(folder["uid"])
            if existing is None:
                planned_folders += 1
                print(f"  CREATE folder: {folder['title']} [{folder['uid']}]")
            elif (existing.get("title") != folder["title"] or
                  (existing.get("parentUid") or "") != (folder.get("parentUid") or "")):
                conflicts += 1
                print(f"  CONFLICT folder: {folder['title']} [{folder['uid']}] differs on destination")
            else:
                print(f"  EXISTS folder: {folder['title']} [{folder['uid']}]")
        for record in records:
            existing = new.dashboard(record["uid"])
            blockers = [w for w in record["warnings"] if "datasource" in w.lower() or "Folder " in w]
            if blockers and not args.allow_unmatched_datasources:
                conflicts += 1
                print(f"  BLOCKED dashboard: {record['title']} [{record['uid']}], unmatched datasource/folder")
            elif existing:
                existing_dashboards += 1
                print(f"  EXISTS dashboard: {record['title']} [{record['uid']}]")
            else:
                planned_dashboards += 1
                print(f"  CREATE dashboard: {record['title']} [{record['uid']}]")
        print(f"\nDRY RUN SUMMARY: create {planned_folders} folders, "
              f"{planned_dashboards} dashboards, {existing_dashboards} existing dashboards, "
              f"{conflicts} conflicts/blockers")
        print("No changes made. Run with --apply to create missing items.")
        return 1 if conflicts else 0

    failed = 0
    folder_ready = {""}
    for folder in old_folders:
        uid = folder["uid"]
        parent = folder.get("parentUid") or ""
        if parent not in folder_ready:
            print(f"ERROR folder {uid}: parent {parent} not available; skipping")
            failed += 1
            continue
        try:
            existing = new.folder(uid)
            if existing:
                if (existing.get("title") != folder["title"] or
                        (existing.get("parentUid") or "") != parent):
                    raise MigrationError("UID conflict: destination folder title/parent differs")
                print("SKIP existing folder:", folder["title"], uid)
            else:
                payload = {"uid": uid, "title": folder["title"]}
                if parent:
                    payload["parentUid"] = parent
                new.post("/api/folders", payload)
                print("CREATE folder:", folder["title"], uid)
            folder_ready.add(uid)
        except MigrationError as exc:
            print(f"ERROR folder {uid}: {exc}")
            failed += 1

    counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    for record in records:
        uid = record["uid"]
        if record["folderUid"] not in folder_ready:
            print(f"ERROR dashboard {uid}: destination folder unavailable")
            counts["failed"] += 1
            continue
        if record["warnings"] and not args.allow_unmatched_datasources:
            # Only block datasource errors, not informational warnings about legacy panel features.
            blockers = [w for w in record["warnings"] if "datasource" in w.lower() or "Folder " in w]
            if blockers:
                print(f"ERROR dashboard {uid}: datasource/folder mismatch (see warnings above)")
                counts["failed"] += 1
                continue
        try:
            existing = new.dashboard(uid)
            if existing and not args.overwrite:
                print("SKIP existing dashboard:", record["title"], uid)
                counts["skipped"] += 1
                continue
            # Never use 'overwrite' as an import shortcut. Only explicit --overwrite.
            payload = {"dashboard": record["dashboard"],
                       "folderUid": record["folderUid"],
                       "overwrite": args.overwrite,
                       "message": "Migration from Grafana 10"}
            new.post("/api/dashboards/db", payload)
            action = "updated" if existing else "created"
            print(f"{action.upper()} dashboard: {record['title']} [{uid}]")
            counts[action] += 1
        except MigrationError as exc:
            print(f"ERROR dashboard {uid}: {exc}")
            counts["failed"] += 1

    save_json(backup_dir / "result.json", {"counts": counts, "folder_errors": failed})
    print("\nRESULT:", counts, "folder errors:", failed)
    return 1 if failed or counts["failed"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (MigrationError, OSError) as exc:
        print("FATAL:", exc, file=sys.stderr)
        sys.exit(2)
