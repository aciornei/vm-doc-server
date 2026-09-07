cd /usr/local/src/vm-doc-server-0.18.0

python3 - <<'PY'
from pathlib import Path

p = Path("internal/veeam/client.go")
s = p.read_text()

s = s.replace(
    'PlatformName       string `json:"platformName"`',
    'PlatformName       any    `json:"platformName"`'
)
s = s.replace(
    'PlatformName   string `json:"platformName"`',
    'PlatformName   any    `json:"platformName"`'
)
s = s.replace(
    'PlatformName string `json:"platformName"`',
    'PlatformName any    `json:"platformName"`'
)

p.write_text(s)
print("OK - platformName accepta acum string sau numar")
PY

gofmt -w internal/veeam/client.go

GOPROXY=off GOFLAGS=-mod=vendor go test ./...
