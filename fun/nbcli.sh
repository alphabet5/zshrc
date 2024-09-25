nb () {
  nbcli filter device $1 --json | jq -r '["NAME", "ENV", "PURPOSE", "BMC", "PLATFORM"],(.[] | [.name, .custom_fields.environment, .custom_fields.purpose,.custom_fields.bmc_ip4,.platform.name]) | @tsv' | python3 $MYDIR/python/prettytable.py 
}
