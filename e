cd /usr/local/src/vm-doc-server-0.18.2

python3 - <<'PY'
from pathlib import Path

p = Path("internal/veeam/service.go")
s = p.read_text()

# 1. Fix salvare cron manual
s = s.replace(
    "VALUES(?,'manual',0,?,?,?,'') ON DUPLICATE KEY UPDATE",
    "VALUES(?,'manual',0,?,?,?,?,'') ON DUPLICATE KEY UPDATE"
)

# 2. Fix INSERT pentru VM protejate de Veeam
s = s.replace(
    "synced_at,error_message,raw_json)",
    "synced_at,error_message,raw_json,cron_backup_notes)",
    1
)

s = s.replace(
    "VALUES(?,'veeam',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    "VALUES(?,'veeam',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'')",
    1
)

# 3. Fix INSERT pentru VM neprotejate
s = s.replace(
    "restore_points,synced_at,error_message)",
    "restore_points,synced_at,error_message,cron_backup_notes)",
    1
)

s = s.replace(
    "VALUES(?,'veeam',?,?,0,'','','','',0,?,'')",
    "VALUES(?,'veeam',?,?,0,'','','','',0,?,'','')",
    1
)

p.write_text(s)
print("OK - INSERT-urile Veeam si cron au fost corectate")
PY

gofmt -w internal/veeam/service.go
