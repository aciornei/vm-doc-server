cd /usr/local/src/vm-doc-server-0.18.0

python3 - <<'PY'
from pathlib import Path
import re

p = Path("internal/veeam/client.go")
s = p.read_text()

s, n = re.subn(
    r'(?m)^(\s*PlatformName\s+)string(\s+`json:"platformName"`)$',
    r'\1any\2',
    s
)

p.write_text(s)

print("Modificari facute:", n)
if n != 3:
    raise SystemExit("EROARE: trebuiau modificate 3 campuri PlatformName")
PY
