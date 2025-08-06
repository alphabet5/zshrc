# Simple histogram

```bash
grep 'SLOW PAGE' error.log | grep -E "took [0-9][0-9][0-9][0-9][0-9] ms" | cut -b1-11 | uniq -c | tail -n 20
     30 Jun  3 06:4
     23 Jun  3 06:5
    834 Jun  3 07:0
     34 Jun  3 07:1
     39 Jun  3 07:2
     49 Jun  3 07:3
      8 Jun  3 07:4
```

