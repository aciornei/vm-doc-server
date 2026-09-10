Dacă ai deja userul Linux de la MariaDB:

id vm-doc-inventory

nu mai trebuie creat. Altfel:

useradd --system --no-create-home --shell /usr/sbin/nologin vm-doc-inventory

Intră în PostgreSQL ca postgres:

su - postgres -c "psql -d postgres"

și creează rolul:

CREATE ROLE "vm-doc-inventory" LOGIN;

GRANT CONNECT ON DATABASE postgres
TO "vm-doc-inventory";

Nu îi dai SUPERUSER, CREATEDB, SELECT pe bazele aplicațiilor etc.

Vezi unde este pg_hba.conf:

SHOW hba_file;

În acel fișier pune înaintea regulilor locale generale:

local   postgres   vm-doc-inventory   peer
local   all        vm-doc-inventory   reject

A doua linie este intenționată: userul de inventariere poate intra în baza tehnică postgres, dar este refuzat explicit pentru celelalte baze.

Nu trebuie restart PostgreSQL. Poți face:

SELECT pg_reload_conf();

Apoi testul:

runuser -u vm-doc-inventory -- \
  psql -AtX -w \
  -U vm-doc-inventory \
  -d postgres \
  -c "SELECT datname FROM pg_database WHERE datistemplate=false ORDER BY datname"

Trebuie să îți returneze numele bazelor fără să ceară parolă.

Am adăugat și -w în agent, deci psql nu va încerca niciodată să ceară interactiv o parolă.
