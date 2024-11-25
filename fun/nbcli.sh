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

function nb-interface() {
  curl -H "Authorization: Token $NETBOX_TOKEN" \
  -H "Content-Type: application/json" "$NETBOX_URL/api/dcim/interfaces/${1}/" 2>/dev/null | jq
}

function nb-devices() {
  curl -H "Authorization: Token $NETBOX_TOKEN" \
  -H "Content-Type: application/json" "$NETBOX_URL/api/dcim/devices/?limit=0" 2>/dev/null | jq
}
