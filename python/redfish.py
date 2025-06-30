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
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import traceback

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CustomSSLContextHTTPAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = urllib3.poolmanager.PoolManager(
            num_pools=connections, maxsize=maxsize,
            block=block, ssl_context=self.ssl_context)

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

def run(hostinfo, path="", patch="", post="", bios=False):
    ctx = urllib3.util.create_urllib3_context()
    ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    ctx.check_hostname = False
    session = requests.session()
    session.adapters.pop("https://", None)
    session.mount("https://", CustomSSLContextHTTPAdapter(ctx))
    host = hostinfo[1]
    name = hostinfo[0]
    if host is None:
        return {'host': name, 'ip': host, 'output': "Error: No bmc IP found."}
    try:
        if bios:
            i = session.get(
                f"https://{host}/redfish/v1/Systems/1",
                verify=False,
                auth=bmc_auth,
            )
            if i.status_code == 404:
                i = session.get(
                    f"https://{host}/redfish/v1/Systems/System.Embedded.1",
                    verify=False,
                    auth=bmc_auth,
                )
            try:
                info = i.json()
            except json.JSONDecodeError:
                logger.error(json.dumps({'error': "Failed to decode JSON response.", 'host': name}))
                logger.error("{" + f'Status: {i.status_code}, "text": {i.text}' + "]")
                return {'host': name, 'ip': host, 'output': "Error: Failed to decode JSON response."}
            return {'host': name, 'ip': host, 'output': info}
        elif len(patch) > 0:
            i = session.patch(
                f"https://{host}/{path}",
                verify=False,
                auth=bmc_auth,
                json=json.loads(patch),
            )
            try:
                info = i.json()
            except:
                logger.error(json.dumps({'error': "Failed to decode JSON response.", 'host': name}))
                logger.error("{" + f'Status: {i.status_code}, "text": {i.text}' + "}")
                info = i.text
        elif len(post) > 0:
            i = session.post(
                f"https://{host}/{path}",
                verify=False,
                auth=bmc_auth,
                json=json.loads(post),
            )
            try:
                info = i.json()
            except:
                logger.error(json.dumps({'error': "Failed to decode JSON response.", 'host': name}))
                logger.error("{" + f'Status: {i.status_code}, "text": {i.text}' + "}")
                info = i.text
        else:
            try:
                tries = 0
                retry = True
                while tries <= 5 and retry:
                    i = session.get(
                        f"https://{host}/{path}",
                        verify=False,
                        auth=bmc_auth,
                    )
                    if i.status_code >= 500:
                        retry = True
                    else:
                        retry = False
            except requests.exceptions.ConnectTimeout as e:
                logger.error(f"Connection error for host {name}: {e}")
                return {'host': name, 'ip': host, 'output': "Error: Connection failed."}
            except:
                logger.error(f"Unexpected error for host {name}: {sys.exc_info()[0]}")
                return {'host': name, 'ip': host, 'output': f"Error: Unexpected error. {traceback.format_exc()}"}
            try:
                info = i.json()
            except json.JSONDecodeError:
                logger.error(json.dumps({'error': "Failed to decode JSON response.", 'host': name}))
                logger.error("{" + f'Status: {i.status_code}, "text": {i.text}' + "}")
                info = i.text
        return {'host': name, 'ip': host, 'output': info}
    except requests.exceptions.ConnectTimeout as e:
        logger.error(f"Connection error for host {name}: {e}")
        return {'host': name, 'ip': host, 'output': "Error: Connection timeout."}
    except:
        logger.error(f"Unexpected error for host {name}: {sys.exc_info()[0]}")
        return {'host': name, 'ip': host, 'output': f"Error: Unexpected error. {traceback.format_exc()}"}

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
    parser.add_argument(
        "--patch",
        type=str,
        default="",
        help="Custom json patch to apply to the specified path."
    )
    parser.add_argument(
        "--post",
        type=str,
        default="",
        help="Custom json post to apply to the specified path."
    )
    args = parser.parse_args()
    if args.netbox:
        hosts = []
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
                    logger.error(traceback.format_exc())
                    pass
            hosts.append((host, bmc_ip))
    else:
        hosts = [(host, host) for host in args.hosts]
    if len(args.path) > 0 or args.bios:
        with ThreadPoolExecutor(max_workers=80) as ex:
            # Use map to call run(hostinfo, path, patch, bios) for each hostinfo
            results = list(tqdm(ex.map(
                    lambda hostinfo: run(
                        hostinfo=hostinfo,
                        path=args.path,
                        patch=args.patch,
                        post=args.post,
                        bios=args.bios
                    ),
                    hosts
                ), total=len(hosts)))
            for res in results:
                print(json.dumps(res))
        # futures = []
        # ex = ThreadPoolExecutor(max_workers=80)
        # for hostinfo in hosts:
        #     # host_list.append({"hostname": host})
        #     futures.append(ex.submit(run, hostinfo=hostinfo, path=args.path, patch=args.patch, bios=args.bios))
        # for future in futures:
        #     res = future.result()
        #     print(json.dumps(res))
