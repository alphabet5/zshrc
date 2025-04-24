import argparse
import json
import time
import os
import logging
import sys
import sys
import os
import requests
from time import sleep
import urllib3
import json
from nb import netbox, get_device
import logging
import ipaddress
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))
log_level = os.getenv("LOG_LEVEL", "INFO")
match log_level:
    case "DEBUG":
        logger.setLevel(logging.DEBUG)
    case "INFO":
        logger.setLevel(logging.INFO)
    case "WARNING":
        logger.setLevel(logging.WARNING)
    case "ERROR":
        logger.setLevel(logging.ERROR)
    case _:
        logger.setLevel(logging.INFO)

if __name__ == "__main__":
    bmc_auth = (os.getenv("REDFISH_USER"), os.getenv("REDFISH_PASSWORD"))
    
    logger = logging.getLogger(__name__)
    parser = argparse.ArgumentParser(
        description="Fetch info via redfish."
    )
    parser.add_argument(
        "hosts", nargs="*", help="List of hostnames or IP addresses to connect to."
    )
    parser.add_argument(
        "--bios",
        action='store_true',
        help="Fetch BIOS version from redfish."
    )
    parser.add_argument(
        "--timing",
        type=int,
        default=0,
        help="Optional, set the delay_factor, and run commands with send_command_timing.",
    )
    parser.add_argument(
        "--netbox",
        action='store_true',
        help="Fetch bmc ip from netbox."
    )
    parser.add_argument(
        "--path",
        type=str,
        default="",
        help="Custom redfish path to fetch."
    )
    args = parser.parse_args()
    if args.netbox:
        hosts = list()
        for host in args.hosts:
            device = get_device(host)['results'][0]
            bmc_ok = False
            bmc_ip = None
            try:
                bmc_ok = bool(
                    ipaddress.ip_address(device["custom_fields"]["bmc_ip4"])
                )
                bmc_ip = device["custom_fields"]["bmc_ip4"]
            except:
                # try to get bmc ip from "mgmt" interface
                bmc_ip = None
                try:
                    ips = netbox(path=f"/api/ipam/ip-addresses/", params={"device_id": device["id"]}).json()
                    for ip in ips["results"]:
                        if ip["assigned_object"]["display"].lower() == "mgmt":
                            bmc_ok = True
                            remove_netmask = re.match(r"(.*)/.*", ip["address"]).group(1)
                            bmc_ok = bool(ipaddress.ip_address(remove_netmask))
                            bmc_ip = remove_netmask
                            break
                except:
                    import traceback
                    print(traceback.format_exc())
                    pass
            hosts.append(bmc_ip)
    else:
        hosts = args.hosts
    if args.bios:
        for i in range(len(hosts)):
            host = hosts[i]
            name = args.hosts[i]
            info = requests.get(
                f"https://{host}/redfish/v1/Systems/1",
                verify=False,
                auth=bmc_auth,
            ).json()
            print(json.dumps({'host': name, 'output': info}))
    if len(args.path) > 0:
        for i in range(len(hosts)):
            host = hosts[i]
            name = args.hosts[i]
            print(host)
            print(name)
            if host is None:
                print(json.dumps({'error': "No bmc IP found.", 'host': name}))
                break
            info = requests.get(
                f"https://{host}/{args.path}",
                verify=False,
                auth=bmc_auth,
            ).json()
            print(json.dumps({'host': name, 'output': info}))
