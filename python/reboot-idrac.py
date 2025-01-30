import sys
import os
import requests
import re
import ipaddress
from time import sleep
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if __name__ == "__main__":
    # Get the device from netbox
    nb_url = os.getenv("NETBOX_URL")
    nb_token = os.getenv("NETBOX_TOKEN")
    nb_headers = {"Authorization": f"Token {nb_token}", "Accept": "application/json"}
    device = requests.get(
        f"{nb_url}/api/dcim/devices/",
        headers=nb_headers,
        params={"name__ic": sys.argv[2]},
    ).json()
    if device["count"] != 1:
        for d in device["results"]:
            print(d["name"])
        raise Exception(f"Multiple devices found for {sys.argv[1]}")
    else:
        device = device["results"][0]
    bmc_ok = False
    try:
        ips = requests.get(
            f"{nb_url}/api/ipam/ip-addresses/",
            headers=nb_headers,
            params={"device_id": device["id"]},
        ).json()
        for ip in ips["results"]:
            if ip["assigned_object"]["display"].lower() == "mgmt":
                bmc_ok = True
                remove_netmask = re.match(r"(.*)/.*", ip["address"]).group(1)
                bmc_ok = bool(ipaddress.ip_address(remove_netmask))
                bmc_ip = remove_netmask
                break
    except:
        pass
    if not bmc_ok:
        bmc_ok = bool(ipaddress.ip_address(device["custom_fields"]["bmc_ip4"]))
        bmc_ip = device["custom_fields"]["bmc_ip4"]
    if not bmc_ok:
        print(
            "Check netbox to make sure the host is configured correctly. No management IP found."
        )
        sys.exit(1)
    else:
        idrac_auth = (os.getenv("IDRAC_USER"), os.getenv("IDRAC_PASSWORD"))
        if sys.argv[1] == "reboot":
            if input(f"Reboot {device['name']}? (y/n) ") == "y":
                print(f"BMC IP: {bmc_ip}")
                # Force Off
                print("Forcing Off")
                r = requests.post(
                    f"https://{bmc_ip}/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
                    json={"ResetType": "ForceOff"},
                    verify=False,
                    auth=idrac_auth,
                )
                print(f"{device['name']} - {r.status_code}")
                print(f"{device['name']} - {r.text}")
                print("Waiting 10 seconds...")
                sleep(10)
                # Force On
        if sys.argv[1] in ["boot", "reboot"]:
            print(f"{device['name']} - Powering Up")
            r = requests.post(
                f"https://{bmc_ip}/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
                json={"ResetType": "On"},
                verify=False,
                auth=idrac_auth,
            )
            print(f"{device['name']} - {r.status_code}")
            print(f"{device['name']} - {r.text}")
