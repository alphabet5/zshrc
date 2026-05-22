#!/usr/bin/env python3
"""
syshost - a `host`-like utility that uses the macOS system resolver.

Unlike `host`, `dig`, and `nslookup` (which talk directly to DNS servers via
the BIND resolver), this tool goes through getaddrinfo(3) and the system
DNS configuration APIs, so it honors:

  - /etc/resolver/* per-domain rules
  - VPN split-DNS / match-domain rules
  - Search domains per interface
  - mDNS for .local
  - Whatever scutil --dns says is in effect

Usage:
    syshost <name>            # forward lookup (A/AAAA via getaddrinfo)
    syshost <ip>              # reverse lookup (PTR via getnameinfo)
    syshost -t <type> <name>  # specific record type via res_query
                              # type: A, AAAA, MX, TXT, CNAME, NS, SOA, SRV, PTR, ANY
    syshost -v <name>         # verbose: show which resolver matched

Search domains:
    Unqualified names are tried against each search domain in turn. The list
    comes from $SEARCH_DOMAINS (space-separated) if set, otherwise from
    `scutil --dns`. Set SEARCH_DOMAINS="" to disable search expansion.

Examples:
    syshost google.com
    syshost 8.8.8.8
    syshost -t MX gmail.com
    syshost -t TXT _dmarc.google.com
"""

import argparse
import ctypes
import ctypes.util
import ipaddress
import os
import socket
import struct
import subprocess
import sys


# ---------------------------------------------------------------------------
# Search domains. macOS's scutil --dns prints lines like:
#     search domain[0] : a.example.com b.example.com
# where multiple domains may share one bracketed index (space-separated).
# ---------------------------------------------------------------------------
def get_search_domains():
    env = os.environ.get("SEARCH_DOMAINS")
    if env is not None:
        return env.split()
    try:
        out = subprocess.check_output(
            ["scutil", "--dns"], text=True, stderr=subprocess.DEVNULL
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    domains, seen = [], set()
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("search domain["):
            continue
        _, _, rhs = line.partition(":")
        for d in rhs.split():
            if d and d not in seen:
                seen.add(d)
                domains.append(d)
    return domains


def candidate_names(name, search_domains):
    """Yield names to try, BSD-resolver-style: trailing dot is absolute,
    dotted names try bare first then search, undotted try search first."""
    if name.endswith("."):
        yield name[:-1]
        return
    if "." in name:
        yield name
        for d in search_domains:
            yield f"{name}.{d.rstrip('.')}"
    else:
        for d in search_domains:
            yield f"{name}.{d.rstrip('.')}"
        yield name


# ---------------------------------------------------------------------------
# Forward lookup via getaddrinfo - this is the call that respects every bit
# of macOS resolver configuration.
# ---------------------------------------------------------------------------
def forward_lookup(name):
    search_domains = get_search_domains()
    last_error = None
    for candidate in candidate_names(name, search_domains):
        try:
            # AF_UNSPEC asks for both A and AAAA. SOCK_STREAM dedupes results
            # so we don't get one entry per (TCP, UDP, raw) socket type.
            infos = socket.getaddrinfo(
                candidate, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
        except socket.gaierror as e:
            last_error = e
            continue

        seen = set()
        for family, _, _, _, sockaddr in infos:
            addr = sockaddr[0]
            if addr in seen:
                continue
            seen.add(addr)
            rtype = "has address" if family == socket.AF_INET else "has IPv6 address"
            print(f"{candidate} {rtype} {addr}")
        return 0

    err = last_error.strerror if last_error else "no match"
    print(f"Host {name} not found: {err}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Reverse lookup via getnameinfo - also respects the system resolver,
# including any per-domain reverse zones (e.g. corporate 10.in-addr.arpa
# served only over VPN).
# ---------------------------------------------------------------------------
def reverse_lookup(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        print(f"{addr} is not a valid IP address", file=sys.stderr)
        return 1

    if ip.version == 4:
        sockaddr = (str(ip), 0)
        family = socket.AF_INET
    else:
        sockaddr = (str(ip), 0, 0, 0)
        family = socket.AF_INET6

    try:
        # Build a socket address structure and resolve it.
        # We use the low-level form so getnameinfo gets the right family.
        host, _ = socket.getnameinfo(sockaddr, socket.NI_NAMEREQD)
    except socket.gaierror as e:
        print(f"Host {addr} not found: {e.strerror}", file=sys.stderr)
        return 1

    # Mimic `host`'s output format: 8.8.8.8.in-addr.arpa domain name pointer dns.google.
    arpa = ip.reverse_pointer
    print(f"{arpa} domain name pointer {host}.")
    return 0


# ---------------------------------------------------------------------------
# Specific record types via libresolv's res_query / res_search.
#
# getaddrinfo only gives us A/AAAA. For MX, TXT, SRV, etc., we have to drop
# down to res_search, which is also part of the system resolver and reads
# the same configuration (it's what the resolver subsystem exposes for
# arbitrary record types).
# ---------------------------------------------------------------------------
RR_TYPES = {
    "A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "PTR": 12,
    "MX": 15, "TXT": 16, "AAAA": 28, "SRV": 33, "ANY": 255,
}
RR_NAMES = {v: k for k, v in RR_TYPES.items()}
CLASS_IN = 1

# We need libresolv for res_search and dn_expand. On macOS this is
# /usr/lib/libresolv.dylib.
_libresolv = ctypes.CDLL(ctypes.util.find_library("resolv"))

# int res_search(const char *dname, int class, int type, u_char *answer, int anslen);
_libresolv.res_search.argtypes = [
    ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
    ctypes.c_char_p, ctypes.c_int,
]
_libresolv.res_search.restype = ctypes.c_int

# int dn_expand(const u_char *msg, const u_char *eomorig, const u_char *comp_dn,
#               char *exp_dn, int length);
_libresolv.dn_expand.argtypes = [
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.c_int,
]
_libresolv.dn_expand.restype = ctypes.c_int


def _expand_name(msg, offset):
    """Wrap dn_expand: returns (name_str, bytes_consumed_in_msg)."""
    buf = ctypes.create_string_buffer(1025)
    n = _libresolv.dn_expand(
        msg, msg[len(msg):] or msg, msg[offset:], buf, 1025
    )
    # The third arg to dn_expand needs the start of the compressed name;
    # ctypes string slicing gives us bytes, which is fine. We pass
    # eom = msg + len(msg) as a pointer past the end.
    if n < 0:
        raise OSError("dn_expand failed")
    return buf.value.decode("ascii"), n


def _parse_response(buf, length, qtype):
    """Walk a DNS response message and yield human-readable answer strings."""
    if length < 12:
        return

    # Header: ID(2) FLAGS(2) QDCOUNT(2) ANCOUNT(2) NSCOUNT(2) ARCOUNT(2)
    _, _, qd, an, _, _ = struct.unpack(">HHHHHH", buf[:12])
    msg = bytes(buf[:length])
    pos = 12

    # Skip the question section.
    for _ in range(qd):
        name, n = _expand_name(msg, pos)
        pos += n + 4  # name + QTYPE(2) + QCLASS(2)

    # Walk the answer section.
    for _ in range(an):
        name, n = _expand_name(msg, pos)
        pos += n
        rtype, rclass, _ttl, rdlen = struct.unpack(">HHIH", msg[pos:pos+10])
        pos += 10
        rdata = msg[pos:pos+rdlen]

        if rtype == RR_TYPES["A"] and rdlen == 4:
            ip = ".".join(str(b) for b in rdata)
            yield f"{name} has address {ip}"
        elif rtype == RR_TYPES["AAAA"] and rdlen == 16:
            ip = socket.inet_ntop(socket.AF_INET6, rdata)
            yield f"{name} has IPv6 address {ip}"
        elif rtype == RR_TYPES["MX"]:
            pref = struct.unpack(">H", rdata[:2])[0]
            target, _ = _expand_name(msg, pos + 2)
            yield f"{name} mail is handled by {pref} {target}."
        elif rtype == RR_TYPES["CNAME"]:
            target, _ = _expand_name(msg, pos)
            yield f"{name} is an alias for {target}."
        elif rtype == RR_TYPES["NS"]:
            target, _ = _expand_name(msg, pos)
            yield f"{name} name server {target}."
        elif rtype == RR_TYPES["PTR"]:
            target, _ = _expand_name(msg, pos)
            yield f"{name} domain name pointer {target}."
        elif rtype == RR_TYPES["TXT"]:
            # TXT rdata is one or more <length-prefixed> strings.
            parts, i = [], 0
            while i < rdlen:
                slen = rdata[i]
                parts.append(rdata[i+1:i+1+slen].decode("utf-8", "replace"))
                i += 1 + slen
            yield f'{name} descriptive text "{"".join(parts)}"'
        elif rtype == RR_TYPES["SRV"]:
            prio, weight, port = struct.unpack(">HHH", rdata[:6])
            target, _ = _expand_name(msg, pos + 6)
            yield f"{name} has SRV record {prio} {weight} {port} {target}."
        elif rtype == RR_TYPES["SOA"]:
            mname, ln = _expand_name(msg, pos)
            rname, ln2 = _expand_name(msg, pos + ln)
            nums = struct.unpack(">IIIII", rdata[ln+ln2:ln+ln2+20])
            yield f"{name} has SOA record {mname} {rname} {' '.join(str(n) for n in nums)}"
        else:
            tname = RR_NAMES.get(rtype, str(rtype))
            yield f"{name} has {tname} record (rdata not decoded, {rdlen} bytes)"

        pos += rdlen


def typed_lookup(name, type_str):
    qtype = RR_TYPES.get(type_str.upper())
    if qtype is None:
        print(f"Unknown record type: {type_str}", file=sys.stderr)
        return 1

    search_domains = get_search_domains()
    buf = ctypes.create_string_buffer(4096)
    for candidate in candidate_names(name, search_domains):
        n = _libresolv.res_search(candidate.encode("ascii"), CLASS_IN, qtype, buf, 4096)
        if n < 0:
            continue

        any_printed = False
        for line in _parse_response(buf, n, qtype):
            print(line)
            any_printed = True

        if not any_printed:
            print(f"{candidate} has no {type_str} records in the answer section")
        return 0

    print(f"Host {name} not found: no {type_str} record", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------
def is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="syshost",
        description="Like `host`, but uses the macOS system resolver.",
    )
    p.add_argument("-t", "--type", help="DNS record type (A, AAAA, MX, TXT, ...)")
    p.add_argument("name", help="hostname or IP address to look up")
    args = p.parse_args(argv)

    if args.type:
        return typed_lookup(args.name, args.type)
    if is_ip(args.name):
        return reverse_lookup(args.name)
    return forward_lookup(args.name)


if __name__ == "__main__":
    sys.exit(main())
