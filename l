docker exec NUME_CONTAINER sh -c \
  'echo "POSTGRES_USER=$POSTGRES_USER"; echo "POSTGRES_DB=$POSTGRES_DB"'


docker exec -u postgres NUME_CONTAINER sh -c \
  'psql -AtX -w \
    -U "$POSTGRES_USER" \
    -d "${POSTGRES_DB:-postgres}" \
    -c "SELECT datname FROM pg_database WHERE datistemplate = false;"'
