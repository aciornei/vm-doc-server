curl -s \
  -X POST 'https://outline.domeniu.ro/api/documents.info' \
  -H "Authorization: Bearer ${OUTLINE_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"id":"IDENTIFICATORUL_PE_CARE_IL_AI_ACUM"}' \
| jq -r '.data.id'
