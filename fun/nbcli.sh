function nb() {
  python3.12 $MYDIR/python/nb.py "$@"
}

# function nb () {
#   nbcli filter device $1 --json | jq -r '["NAME", "ENV", "PURPOSE", "BMC", "PLATFORM", "MODEL", "PARENT", "K8S CLUSTER"],(.[] | [.name, .custom_fields.environment, .custom_fields.purpose,.custom_fields.bmc_ip4,.platform.name, .device_type.display, .parent_device.display, .custom_fields.k8s_cluster]) | @tsv' | python3 $MYDIR/python/prettytable.py 
# }
function nb-device() {
  curl -H "Authorization: Token $NETBOX_TOKEN" \
  -H "Content-Type: application/json" "$NETBOX_URL/api/dcim/devices/${1}/" 2>/dev/null | jq
}

function nb-interfaces() {
  curl -H "Authorization: Token $NETBOX_TOKEN" \
  -H "Content-Type: application/json" "$NETBOX_URL/api/dcim/interfaces/?device_id=${1}" 2>/dev/null | jq
}

function nb-interface() {
  curl -H "Authorization: Token $NETBOX_TOKEN" \
  -H "Content-Type: application/json" "$NETBOX_URL/api/dcim/interfaces/${1}/" 2>/dev/null | jq
}

function nb-devices() {
  last=$(curl -H "Authorization: Token $NETBOX_TOKEN" \
  -H "Content-Type: application/json" "$NETBOX_URL/api/dcim/devices/?limit=10000&status=active&role=server" 2>/dev/null | jq)
  all=$(printf '%s\n' "$last" | jq -rc '.results[]')
  while [ "$(printf '%s\n' "$last" | jq -r '.next')" != "null" ]; do
    next=$(curl -H "Authorization: Token $NETBOX_TOKEN" -H "Content-Type: application/json" "$(printf '%s\n' "$last" | jq -r '.next')" 2>/dev/null | jq)
    all=$all"\n"$(printf '%s\n' "$next" | jq -rc '.results[]')
    last=$next
  done
  printf '%s\n' "$all" | jq -rc
}


update-nb-dns() {
  local csv="$1"

  if [[ -z "$csv" ]]; then
    echo "Usage: update-nb-dns <csv_file>"
    return 1
  fi
  if [[ ! -f "$csv" ]]; then
    echo "File not found: $csv"
    return 1
  fi

  # Read id,dns_name from CSV (no header). Handle missing newline at EOF.
  while IFS=, read -r id dns_name || [[ -n "$id$dns_name" ]]; do
    # Skip blank rows
    [[ -z "$id" || -z "$dns_name" ]] && continue

    # Trim possible trailing CRs (Windows line endings)
    id=${id%$'\r'}
    dns_name=${dns_name%$'\r'}

    echo "Updating ID $id -> $dns_name"

    resp_file=$(mktemp)
    http_code=$(
      curl --silent --show-error --no-progress-meter \
        --request PATCH \
        --header "Authorization: Token $NETBOX_TOKEN" \
        --header "Content-Type: application/json" \
        --header "Accept: application/json" \
        --data "{\"dns_name\":\"$dns_name\"}" \
        --output "$resp_file" \
        --write-out "%{http_code}" \
        "$NETBOX_URL/api/ipam/ip-addresses/$id/"
    )

    if [[ "$http_code" =~ ^2 ]]; then
      echo "✅ $id updated ($http_code)"
    else
      echo "❌ $id failed ($http_code)"
      cat "$resp_file"
    fi
    rm -f "$resp_file"
  done < "$csv"
}


function nb-add-ip() {
  local ip="$1"
  local description="$2"
  local dns="$3"

  local payload
  payload=$(jq -n \
    --arg address "$ip" \
    --arg description "$description" \
    --arg dns "$dns" \
    '{address: $address, status: "active", description: $description, dns_name: $dns}')

  curl -sS -X POST \
    -H "Authorization: Token $NETBOX_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "$NETBOX_URL/api/ipam/ip-addresses/" | jq
}

function nb-add-ips() {
  local input_file="${1:-ips.tsv}"

  if [ ! -f "$input_file" ]; then
    echo "File not found: $input_file" >&2
    return 1
  fi

  tail -n +2 "$input_file" | while IFS=$'\t' read -r ip description dns; do
    [ -z "$ip" ] && continue
    echo "Adding $ip ($description) -> $dns"
    nb-add-ip "$ip" "$description" "$dns"
  done
}
