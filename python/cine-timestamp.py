#!/usr/bin/env python3
import sys
from datetime import datetime, timezone
from pycine.file import read_header

fname = sys.argv[1]

h = read_header(fname)
tt = h['cinefileheader'].TriggerTime

ts = tt.seconds + tt.fractions / 2**32

# print(fname + "\t" + datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
print(fname + "\t" + datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"))
