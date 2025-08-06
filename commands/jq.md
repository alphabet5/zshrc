# Helpful jq commands

## lldp


```bash
run-commands host1 host2 host3 --command 'lldpcli show neighbors -f json | jq -crM' > lldp.json
```

```bash
cat lldp.json | jq -r '
  . as $root |
  $root.output["lldpcli show neighbors -f json | jq -crM"].lldp.interface[]
  | to_entries[]
  | [
      $root.name,
      .key,
      (.value.chassis | to_entries[0].key),
      .value.port.id.value
    ]
  | @csv
'
```

## Capturing regex group

```bash
run-commands host1 host2 --command '
cat os.json | jq -r 'select(.errors == {}) | "\(.name)\t\(.simple | capture("Description:\t(?<desc>.+)") | .desc)"'
```

## CSV Output

```bash
jq -r '.[] 
  | select(.role.id == 8 and .status.value == "active") 
  | [.name, .custom_fields.operating_system, .tenant.display, .custom_fields.purpose, .custom_fields.environment, .device_type.display] 
  | @tsv'
```
