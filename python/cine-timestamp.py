#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import zoneinfo
from pycine.file import read_header

parser = argparse.ArgumentParser(description="Print trigger timestamp from a .cine file")
parser.add_argument("file", help=".cine file path")
parser.add_argument("--tz", default=None, help="Timezone name (e.g. America/Denver). Defaults to tz in cine file, then local time.")
args = parser.parse_args()

h = read_header(args.file)
tt = h['cinefileheader'].TriggerTime

ts = tt.seconds + tt.fractions / 2**32

# Try to get timezone from the cine file header
tz = None
if args.tz:
    tz = zoneinfo.ZoneInfo(args.tz)
else:
    # TriggerTime has a time zone offset in the upper 16 bits of fractions (SMPTE 309M)
    # pycine may also expose it via biases or camera setup
    try:
        camera_setup = h.get('setup', None)
        if camera_setup is not None:
            # TZBias is in minutes, west of UTC (like Windows TIME_ZONE_INFORMATION)
            tz_bias = getattr(camera_setup, 'TZBias', None)
            if tz_bias is not None and tz_bias != 0x7fffffff:
                from datetime import timedelta, timezone as tz_mod
                tz = tz_mod(timedelta(minutes=-tz_bias))
    except Exception:
        pass

dt = datetime.fromtimestamp(ts, tz=tz if tz else timezone.utc)
if not tz and not args.tz:
    # Fall back to local time if no tz info available
    dt = datetime.fromtimestamp(ts)

print(args.file + "\t" + dt.strftime("%Y-%m-%d %H:%M:%S"))
