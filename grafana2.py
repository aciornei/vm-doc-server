#!/usr/bin/env python3
"""Safely migrate ONLY the Grafana organization 'calculator' (Grafana 10 -> 13).

Default is READ-ONLY against Grafana: export source JSON + print a plan.
With --apply, create destination organization if needed, clone non-secret
source datasource configurations, folders and dashboards. Does not overwrite.

Required environment:
    GRAFANA_OLD_URL, GRAFANA_OLD_TOKEN, GRAFANA_NEW_URL
To create the organization, supply a Grafana SERVER admin with Basic Auth:
    GRAFANA_NEW_ADMIN_USER, GRAFANA_NEW_ADMIN_PASSWORD
If organization 'calculator' already exists, a target token scoped to it
can be used instead: GRAFANA_NEW_TOKEN.

Service-account tokens cannot create organizations or switch organizations.
Secrets stored in datasource secureJsonData cannot be recovered through the API.
Does not migrate alerts, library panels, users, permissions, playlists, history.
"""
import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote

try:
    import requests
except ImportError:
    sys.exit('Dependency missing: python3 -m pip install requests')

ORG_NAME = 'calculator'


class MigrationError(Exception):
    pass


class Grafana:
    def __init__(self, url, *, token=None, username=None, password=None, org_id=None,
                 verify=True, timeout=30):
        self.url = url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({'Accept': 'application/json',
                                     'Content-Type': 'application/json'})
        if token:
            self.session.headers['Authorization'] = 'Bearer ' + token
        elif username and password:
            self.session.auth = (username, password)
        else:
            raise MigrationError('Missing token or Basic Auth credentials')
        if org_id is not None:
            self.session.headers['X-Grafana-Org-Id'] = str(org_id)
        self.verify = verify
        self.timeout = timeout

    def request(self, method, path, params=None, payload=None, missing_ok=False):
        try:
            response = self.session.request(method, self.url + path, params=params,
                                            json=payload, verify=self.verify,
                                            timeout=self.timeout)
        except requests.RequestException as exc:
            raise MigrationError(f'{method} {path}: connection/TLS failure: {exc}') from exc
        if missing_ok and response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            msg = response.text.replace('\n', ' ')[:450]
            raise MigrationError(f'{method} {path}: HTTP {response.status_code}: {msg}')
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise MigrationError(f'{method} {path}: response is not JSON') from exc

    def get(self, path, *, params=None, missing_ok=False):
        return self.request('GET', path, params=params, missing_ok=missing_ok)

    def post(self, path, payload):
        return self.request('POST', path, payload=payload)

    def org(self):
        return self.get('/api/org')

    def search(self, kind):
        items = {}
        for page in range(1, 1001):
            batch = self.get('/api/search', params={'type': kind, 'limit': 5000, 'page': page})
            if not isinstance(batch, list):
                raise MigrationError('Grafana /api/search did not return a list')
            for item in batch:
                if item.get('uid'):
                    items[item['uid']] = item
            if len(batch) < 5000:
                return list(items.values())
        raise MigrationError('/api/search exceeded 1000 pages')

    def datasources(self):
        result = self.get('/api/datasources')
        if not isinstance(result, list):
            raise MigrationError('Grafana /api/datasources did not return a list')
        return result

    def dashboard(self, uid):
        return self.get('/api/dashboards/uid/' + quote(uid, safe=''), missing_ok=True)

    def folder(self, uid):
        return self.get('/api/folders/' + quote(uid, safe=''), missing_ok=True)


def validate_org(client, expected=ORG_NAME):
    org = client.org()
    if org.get('name') != expected:
        raise MigrationError(
            f"STOP: token/credentials access organization {org.get('name')!r} "
            f"(ID={org.get('id')}), not {expected!r}. "
            "Create/use a service account token FROM the calculator organization."
        )
    return org


def source_inventory(client):
    """Fetch from a VERIFIED source organization. No other org is accessed."""
    validate_org(client)
    folder_items = []
    for short in client.search('dash-folder'):
        full = client.folder(short['uid'])
        if full is None:
            raise MigrationError('Folder vanished during export: ' + short['uid'])
        folder_items.append({'uid': short['uid'], 'title': full['title'],
                             'parentUid': full.get('parentUid') or ''})
    ordered = order_folders(folder_items)
    dashboards = []
    for short in client.search('dash-db'):
        uid = short['uid']
        exported = client.dashboard(uid)
        if not exported or not isinstance(exported.get('dashboard'), dict):
            raise MigrationError('Unable to export dashboard ' + uid)
        dashboards.append({'uid': uid, 'title': exported['dashboard'].get('title', short.get('title')),
                           'folderUid': exported.get('meta', {}).get('folderUid') or short.get('folderUid') or '',
                           'export': exported})
    sources = client.datasources()
    return ordered, dashboards, sources


def order_folders(items):
    by_uid = {x['uid']: x for x in items}
    output, seen = [], set()

    def visit(uid, ancestors):
        if uid in seen:
            return
        if uid in ancestors:
            raise MigrationError('Cycle in folder hierarchy: ' + uid)
        parent = by_uid[uid]['parentUid']
        if parent:
            if parent not in by_uid:
                raise MigrationError(f'Parent folder {parent} missing for {uid}')
            visit(parent, ancestors | {uid})
        seen.add(uid)
        output.append(by_uid[uid])

    for f in items:
        visit(f['uid'], set())
    return output


def clone_ds_payload(ds):
    # Intentionally do NOT include local numeric IDs, orgId, secureJsonFields,
    # passwords, readOnly, or other output-only fields.
    keys = ('uid', 'name', 'type', 'access', 'url', 'user', 'database',
            'basicAuth', 'basicAuthUser', 'withCredentials', 'isDefault',
            'jsonData')
    return {k: copy.deepcopy(ds[k]) for k in keys if k in ds}


def ds_plan(source, target):
    """Plan imports; conflict on duplicate names with incompatible types."""
    target_by_name = {item.get('name'): item for item in target}
    additions, conflicts = [], []
    for item in source:
        existing = target_by_name.get(item.get('name'))
        if existing is None:
            additions.append(item)
        elif existing.get('type') != item.get('type'):
            conflicts.append(f"{item.get('name')}: type {item.get('type')} in source "
                             f"but {existing.get('type')} in destination")
    return additions, conflicts


def ds_mapping(source, target):
    """Map by (name, type) and prefer existing target datasource UIDs."""
    index = {(x.get('name'), x.get('type')): x for x in target}
    result, missing = {}, []
    for item in source:
        uid = item.get('uid')
        match = index.get((item.get('name'), item.get('type')))
        if not uid or not match or not match.get('uid'):
            missing.append(f"{item.get('name')} ({item.get('type')})")
        else:
            result[uid] = {'uid': match['uid'], 'type': item.get('type')}
    return result, missing


def transform_dashboard(dashboard, ds_map, source_ds):
    result = copy.deepcopy(dashboard)
    by_uid = {x.get('uid'): x for x in source_ds if x.get('uid')}
    by_name = {x.get('name'): x for x in source_ds if x.get('name')}
    special = {'-- Grafana --', '-- Mixed --', 'grafana', '__expr__', '__dashboard__'}
    warnings = set()

    def remap_uid(value, loc):
        if not isinstance(value, str) or not value or value in special or value.startswith('$'):
            return value
        if value in by_uid:
            if value in ds_map:
                return ds_map[value]['uid']
            warnings.add(f'{loc}: datasource {by_uid[value].get("name")} missing')
        return value

    def walk(node, loc='dashboard'):
        if isinstance(node, dict):
            if 'libraryPanel' in node:
                warnings.add('Library panel used; library elements are not migrated')
            if 'alert' in node:
                warnings.add('Legacy panel alert requires manual inspection in Grafana 13')
            for key, val in node.items():
                here = loc + '.' + key
                if key == 'datasource':
                    if isinstance(val, dict) and isinstance(val.get('uid'), str):
                        old_uid = val['uid']
                        new_uid = remap_uid(old_uid, here)
                        val['uid'] = new_uid
                        if old_uid in ds_map:
                            val['type'] = ds_map[old_uid]['type']
                    elif isinstance(val, str):
                        if val in by_name:
                            if by_name[val].get('uid') not in ds_map:
                                warnings.add(f'{here}: datasource {val} missing')
                        else:
                            node[key] = remap_uid(val, here)
                elif key in ('datasourceUid', 'datasource_uid'):
                    node[key] = remap_uid(val, here)
                else:
                    walk(val, here)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f'{loc}[{i}]')

    walk(result)
    for variable in result.get('templating', {}).get('list', []):
        if variable.get('type') != 'datasource':
            continue
        current = variable.get('current') or {}
        val = current.get('value')
        if isinstance(val, str):
            current['value'] = remap_uid(val, 'templating.current')
        elif isinstance(val, list):
            current['value'] = [remap_uid(v, 'templating.current') for v in val]
        for option in variable.get('options') or []:
            if isinstance(option.get('value'), str):
                option['value'] = remap_uid(option['value'], 'templating.options')

    # Grafana DB-local identifiers must not be copied into the other instance.
    result['id'] = None
    result['version'] = 0
    return result, sorted(warnings)


def make_prepared(dashboards, ds_map, sources, backup):
    prepared = []
    for record in dashboards:
        dash, warns = transform_dashboard(record['export']['dashboard'], ds_map, sources)
        uid = record['uid']
        dash['uid'] = uid
        body = {'dashboard': dash, 'folderUid': record['folderUid'],
                'overwrite': False, 'message': 'Grafana 10 calculator -> Grafana 13 calculator'}
        save_json(backup / 'prepared' / (uid + '.json'), body)
        prepared.append({**record, 'payload': body, 'warnings': warns})
    return prepared


def save_json(path, item):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as file:
        json.dump(item, file, indent=2, ensure_ascii=False)
        file.write('\n')


def admin_client(url, verify):
    name = os.environ.get('GRAFANA_NEW_ADMIN_USER')
    password = os.environ.get('GRAFANA_NEW_ADMIN_PASSWORD')
    if name and password:
        return Grafana(url, username=name, password=password, verify=verify)
    if name or password:
        raise MigrationError('Both GRAFANA_NEW_ADMIN_USER and GRAFANA_NEW_ADMIN_PASSWORD are required')
    return None


def find_target_org(admin):
    if not admin:
        return None
    return admin.get('/api/orgs/name/' + quote(ORG_NAME, safe=''), missing_ok=True)


def scoped_target(url, admin, org_id, token, verify):
    """Prefer Basic Auth scoped by explicit org ID; token only if verified."""
    if admin:
        new = Grafana(url, username=os.environ['GRAFANA_NEW_ADMIN_USER'],
                      password=os.environ['GRAFANA_NEW_ADMIN_PASSWORD'],
                      org_id=org_id, verify=verify)
    elif token:
        new = Grafana(url, token=token, verify=verify)
    else:
        raise MigrationError('No credentials for target calculator organization')
    identity = validate_org(new)
    if org_id is not None and str(identity.get('id')) != str(org_id):
        raise MigrationError('Target organization ID mismatch; stopping before any import')
    return new


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true', help='Create target org and import (default: preview only)')
    p.add_argument('--backup-dir', help='Folder for source JSON and prepared JSON')
    p.add_argument('--overwrite', action='store_true', help='Update existing dashboards (requires --apply)')
    p.add_argument('--insecure', action='store_true', help='Disable TLS verification (unsafe)')
    p.add_argument('--ca-bundle', help='Path to trusted CA certificate bundle')
    args = p.parse_args()
    if args.overwrite and not args.apply:
        p.error('--overwrite requires --apply')
    if args.insecure and args.ca_bundle:
        p.error('Use --insecure OR --ca-bundle')
    for key in ('GRAFANA_OLD_URL', 'GRAFANA_NEW_URL', 'GRAFANA_OLD_TOKEN'):
        if not os.environ.get(key):
            p.error(f'Missing environment variable {key}')
    old_url, new_url = os.environ['GRAFANA_OLD_URL'], os.environ['GRAFANA_NEW_URL']
    if old_url.rstrip('/') == new_url.rstrip('/'):
        p.error('Source and target Grafana URLs cannot be identical')
    if not all(x.startswith(('http://', 'https://')) for x in (old_url, new_url)):
        p.error('Grafana URLs must use http:// or https://')
    verify = False if args.insecure else args.ca_bundle or True
    if args.insecure:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    os.umask(0o077)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path(args.backup_dir or f'grafana_calculator_backup_{timestamp}')
    old = Grafana(old_url, token=os.environ['GRAFANA_OLD_TOKEN'], verify=verify)
    admin = admin_client(new_url, verify)
    token = os.environ.get('GRAFANA_NEW_TOKEN')
    if not admin and not token:
        p.error('Supply Grafana 13 SERVER admin Basic credentials to create calculator, '
                'or GRAFANA_NEW_TOKEN if calculator already exists')

    print('Checking Grafana source organization ...')
    source_org = validate_org(old)
    old_version = old.get('/api/health').get('version', 'unknown')
    print(f"SOURCE: version {old_version}, organization {source_org['name']} (ID={source_org['id']})")
    print('Exporting source organization ...')
    folders, dashboards, sources = source_inventory(old)
    save_json(backup / 'organization.json', {'source_name': ORG_NAME, 'source_id': source_org['id']})
    save_json(backup / 'folders.json', folders)
    save_json(backup / 'datasources_summary.json', [{k: d.get(k) for k in
                         ('uid', 'name', 'type', 'url', 'secureJsonFields')} for d in sources])
    for d in dashboards:
        save_json(backup / 'original' / (d['uid'] + '.json'), d['export'])
    print(f'Exported {len(dashboards)} dashboards, {len(folders)} folders, '
          f'{len(sources)} datasource(s) to {backup.resolve()}')

    print('Checking Grafana 13 destination organization ...')
    new_version = (admin or Grafana(new_url, token=token, verify=verify)).get('/api/health').get('version', 'unknown')
    print('TARGET version:', new_version)
    org_info = find_target_org(admin)
    new = None
    if org_info:
        print(f"Organization {ORG_NAME!r} exists on target (ID={org_info['id']})")
        new = scoped_target(new_url, admin, org_info['id'], token, verify)
    elif not admin:
        # Only target token supplied. We cannot list or create organizations.
        new = scoped_target(new_url, None, None, token, verify)
        org_info = new.org()
        print(f"Organization {ORG_NAME!r} exists on target (ID={org_info['id']})")
    else:
        print(f"Organization {ORG_NAME!r} not present on target")

    # If the target organization doesn't exist, datasource reads/mapping are simulated.
    real_target_ds = new.datasources() if new else []
    to_clone, collisions = ds_plan(sources, real_target_ds)
    proposed_target_ds = real_target_ds + [clone_ds_payload(d) for d in to_clone]
    proposed_mapping, missing_map = ds_mapping(sources, proposed_target_ds)
    records = make_prepared(dashboards, proposed_mapping, sources, backup)
    folder_ids = {f['uid'] for f in folders}
    for d in records:
        if d['folderUid'] and d['folderUid'] not in folder_ids:
            d['warnings'].append('Missing source folder: ' + d['folderUid'])
    for f in folders:
        print('  FOLDER:', f['title'], '[' + f['uid'] + ']')
    for d in records:
        print('  DASHBOARD:', d['title'], '[' + d['uid'] + ']')
        for warning in d['warnings']:
            print('    WARNING:', warning)
    for ds in to_clone:
        secrets = [k for k, present in (ds.get('secureJsonFields') or {}).items() if present]
        print('  DATASOURCE TO CREATE:', ds.get('name'), '[' + str(ds.get('uid')) + ']')
        if secrets:
            print('    WARNING: manually reconfigure encrypted datasource secrets:', ', '.join(secrets))
    for collision in collisions:
        print('  DATASOURCE CONFLICT:', collision)
    for issue in missing_map:
        print('  DATASOURCE UNMATCHED:', issue)
    if not args.apply:
        print('\nDRY RUN: no changes to either Grafana')
        if not new:
            print(f"  WOULD CREATE target organization: {ORG_NAME}")
        print(f'  WOULD CREATE up to {len(to_clone)} datasource(s), {len(folders)} folder(s), '
              f'{len(records)} dashboard(s) (existing items are skipped)')
        print('  Run with --apply after reviewing; requires Basic Auth server admin to create org.')
        return 1 if collisions or missing_map else 0

    if collisions or missing_map:
        raise MigrationError('Datasource conflicts/missing UID; no target changes were made')

    # All source data is backed up before the first target write.
    if new is None:
        if not admin:
            raise MigrationError('Creating organization requires Grafana server admin Basic Auth')
        print(f'Creating new organization {ORG_NAME!r} ...')
        created = admin.post('/api/orgs', {'name': ORG_NAME})
        target_id = created.get('orgId')
        if not target_id:
            raise MigrationError('Organization creation did not return orgId')
        print('CREATED ORGANIZATION:', ORG_NAME, 'id=', target_id)
        new = scoped_target(new_url, admin, target_id, token, verify)

    failed = 0
    for item in to_clone:
        try:
            existing = [x for x in new.datasources() if x.get('name') == item.get('name')]
            if existing:
                if existing[0].get('type') != item.get('type'):
                    raise MigrationError('Datasource name/type conflict')
                print('SKIP existing datasource:', item['name'])
                continue
            new.post('/api/datasources', clone_ds_payload(item))
            print('CREATED datasource:', item['name'])
        except MigrationError as exc:
            failed += 1
            print('ERROR datasource:', item.get('name'), exc)
    actual_ds = new.datasources()
    actual_map, actual_missing = ds_mapping(sources, actual_ds)
    if actual_missing:
        raise MigrationError('Datasource(s) could not be migrated: ' + ', '.join(actual_missing) +
                             '. Organization may already have been created. Rerun after fixing.')
    records = make_prepared(dashboards, actual_map, sources, backup)

    ready = {''}
    for f in folders:
        if f['parentUid'] not in ready:
            print('ERROR folder missing parent:', f['uid'])
            failed += 1
            continue
        try:
            existing = new.folder(f['uid'])
            if existing:
                if (existing.get('title'), existing.get('parentUid') or '') != (f['title'], f['parentUid']):
                    raise MigrationError('Folder UID collision with different title or parent')
                print('SKIP existing folder:', f['title'])
            else:
                data = {'uid': f['uid'], 'title': f['title']}
                if f['parentUid']:
                    data['parentUid'] = f['parentUid']
                new.post('/api/folders', data)
                print('CREATED folder:', f['title'])
            ready.add(f['uid'])
        except MigrationError as exc:
            print('ERROR folder:', f['uid'], exc)
            failed += 1
    counter = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0}
    for d in records:
        if d['folderUid'] not in ready:
            print('ERROR dashboard folder missing:', d['title'])
            counter['failed'] += 1
            continue
        try:
            existing = new.dashboard(d['uid'])
            if existing and not args.overwrite:
                counter['skipped'] += 1
                print('SKIP existing dashboard:', d['title'])
                continue
            body = d['payload']
            body['overwrite'] = args.overwrite
            new.post('/api/dashboards/db', body)
            action = 'updated' if existing else 'created'
            counter[action] += 1
            print(action.upper(), 'dashboard:', d['title'])
        except MigrationError as exc:
            counter['failed'] += 1
            print('ERROR dashboard:', d['title'], exc)

    save_json(backup / 'result.json', {'org': ORG_NAME, 'target_org_id': new.org()['id'],
                                       'dashboards': counter, 'other_failures': failed})
    print('\nDONE:', counter, '| other failures:', failed)
    print('IMPORTANT: set encrypted datasource secrets in Grafana 13 if used.')
    return 1 if failed or counter['failed'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (MigrationError, OSError) as exc:
        print('FATAL:', exc, file=sys.stderr)
        sys.exit(2)
