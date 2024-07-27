
function es-bulk() {
  curl -H content-type:application/x-ndjson -X POST \
    -H "Authorization: Basic ${ELASTIC_CREDENTIALS}" \
    "https://${ELASTIC_HOST}:${ELASTIC_PORT}/_bulk?filter_path=took,errors,items.*.error" \
    -s -w "\n" --data-binary "@-" -v
}
function es-put() {
  curl -H content-type:application/x-ndjson -X PUT \
    -H "Authorization: Basic ${ELASTIC_CREDENTIALS}" \
    "https://${ELASTIC_HOST}:${ELASTIC_PORT}/${1#/}?filter_path=took,errors,items.*.error" \
    -s -w "\n" --data-binary "@-"
}

function es-bulk-file() {
  curl -H content-type:application/x-ndjson -X POST \
    -H "Authorization: Basic ${ELASTIC_CREDENTIALS}" \
    "https://${ELASTIC_HOST}:${ELASTIC_PORT}/_bulk?filter_path=took,errors,items.*.error" \
    -s -w "\n" -T $1 -v
}
