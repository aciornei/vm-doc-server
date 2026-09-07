cd /usr/local/src/vm-doc-server-0.18.0

python3 - <<'PY'
from pathlib import Path

p = Path("internal/config/config_test.go")
s = p.read_text()

old = """\treturn cfg
}"""

new = """\tapplyDefaults(&cfg)
\treturn cfg
}"""

if "applyDefaults(&cfg)" not in s:
    if old not in s:
        raise SystemExit("Nu am gasit locul de modificat")
    s = s.replace(old, new, 1)
    p.write_text(s)

print("OK:", p)
PY

gofmt -w internal/config/config_test.go

GOPROXY=off GOFLAGS=-mod=vendor go test ./...
