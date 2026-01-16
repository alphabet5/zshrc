# disk commands

## event log

```bash
sudo MegaCli64 -AdpEventLog -GetEvents -f events.log -aALL
```

## list overview info

```bash
sudo MegaCli64 -PDList -aALL
```

## indicator

```bash
sudo MegaCli64 -pdlocate -start -PhysDrv[0:4] -a0
```

## force drive to be ok again

```bash
sudo MegaCli64 -PDMakeGood -PhysDrv[32:0] -aALL
sudo MegaCli64 -PDOnline   -PhysDrv[32:0] -aALL
```

if it refuses
```bash
sudo MegaCli64 -CfgForeign -Clear -aALL
```