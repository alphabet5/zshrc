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

function nb-device-interfaces() {
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
