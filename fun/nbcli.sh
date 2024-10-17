function nb () {
  nbcli filter device $1 --json | jq -r '["NAME", "ENV", "PURPOSE", "BMC", "PLATFORM", "MODEL", "PARENT"],(.[] | [.name, .custom_fields.environment, .custom_fields.purpose,.custom_fields.bmc_ip4,.platform.name, .device_type.display, .parent_device.display]) | @tsv' | python3 $MYDIR/python/prettytable.py 
}
