#!/usr/bin/env python3
import socket
import sys
import argparse
import dns.resolver

def reverse_lookup_with_nameserver(ip, nameserver=None):
    """Perform reverse DNS lookup with optional custom nameserver"""
    if nameserver:
        # Use dnspython for custom nameserver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = [nameserver]
        try:
            result = resolver.resolve_address(ip)
            return str(result[0]).rstrip('.')
        except Exception as e:
            raise Exception(f"DNS lookup failed: {e}")
    else:
        # Use system default nameserver
        return socket.getnameinfo((ip, 0), 0)[0]

def main():
    parser = argparse.ArgumentParser(description='Perform reverse DNS lookups on IP addresses')
    parser.add_argument('--ns', '--nameserver', dest='nameserver', 
                       help='Custom nameserver to use (e.g., 1.1.1.1)')
    parser.add_argument('ips', nargs='*', help='IP addresses to lookup')
    
    args = parser.parse_args()
    
    # If no IPs provided as arguments, read from remaining sys.argv
    if not args.ips:
        # Skip script name and any --ns arguments
        ip_args = []
        skip_next = False
        for i, arg in enumerate(sys.argv[1:], 1):
            if skip_next:
                skip_next = False
                continue
            if arg in ['--ns', '--nameserver']:
                skip_next = True
                continue
            if not arg.startswith('--'):
                ip_args.append(arg)
        
        # Process the remaining arguments as groups
        for group in ip_args:
            for ip in group.split("\n"):
                ip = ip.strip()
                if ip:
                    try:
                        hostname = reverse_lookup_with_nameserver(ip, args.nameserver)
                        print(hostname)
                    except Exception as e:
                        print(f"{ip} {e}")
    else:
        # Process IPs provided as proper arguments
        for ip in args.ips:
            ip = ip.strip()
            if ip:
                try:
                    if '\n' in ip:
                        # If the IP contains newlines, split it
                        for sub_ip in ip.split('\n'):
                            sub_ip = sub_ip.strip()
                            if sub_ip:
                                hostname = reverse_lookup_with_nameserver(sub_ip, args.nameserver)
                                print(hostname)
                    else:
                        # Single IP address
                        hostname = reverse_lookup_with_nameserver(ip, args.nameserver)
                        print(hostname)
                except Exception as e:
                    print(f"{ip} {e}")

if __name__ == "__main__":
    main()