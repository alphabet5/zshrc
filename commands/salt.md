# random salt commands

```bash
sudo salt --batch-size=3 --batch-wait=10 -L "$(cat  final-syslog-clean.list)" state.apply test.ping
```

```bash
head -n2 final-syslog-clean.list
hostname.example.com
host2.example.com
```
