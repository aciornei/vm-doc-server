read -rsp "Outline API key: " OUTLINE_KEY
echo

curl -i \
  -X POST 'https://OUTLINE.DOMENIU.RO/api/auth.info' \
  -H "Authorization: Bearer ${OUTLINE_KEY}" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{}'
