cd /usr/local/src/vm-doc-server-0.18.0

python3 - <<'PY'
from pathlib import Path
import re

p = Path("internal/veeam/client.go")
s = p.read_text()

pattern = r'''func \(c \*Client\) Test\(ctx context\.Context\) \(ServerInfo, int, error\) \{.*?\n\}\n\nfunc \(c \*Client\) Inventory'''

replacement = '''func (c *Client) Test(ctx context.Context) (ServerInfo, int, error) {
	token, err := c.login(ctx)
	if err != nil {
		return ServerInfo{}, 0, err
	}

	// Test read-only: nu folosim /serverInfo deoarece poate cere drepturi administrative.
	var page backupObjectResult
	if err := c.get(ctx, token, "/api/v1/backupObjects", url.Values{"skip": {"0"}, "limit": {"1"}}, &page); err != nil {
		return ServerInfo{}, 0, fmt.Errorf("read Veeam backup objects: %w", err)
	}

	total := page.Pagination.Total
	if total == 0 {
		total = len(page.Data)
	}

	return ServerInfo{}, total, nil
}

func (c *Client) Inventory'''

s, n = re.subn(pattern, replacement, s, flags=re.S)

if n != 1:
    raise SystemExit(f"EROARE: functia Test nu a fost gasita corect. Modificari={n}")

p.write_text(s)
print("OK - Test Veeam modificat pentru Backup Viewer")
PY

gofmt -w internal/veeam/client.go
