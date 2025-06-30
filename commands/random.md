# Random commands 


## inodes

```
{ find / -xdev -printf '%h\n' | sort | uniq -c | sort -k 1 -n; } 2>/dev/null
```