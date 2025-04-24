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
        bmc_auth = (os.getenv("REDFISH_USER"), os.getenv("REDFISH_PASSWORD"))
        info = requests.get(
            f"https://{bmc_ip}/redfish/v1/",
            verify=False,
            auth=bmc_auth,
        ).json()
        if sys.argv[1] in ["pxe"]:
            confirm = input(
                f"Set 1-time pxe boot and force a reboot for {device['name']}? (Vendor {info['Vendor']}) (y/n) "
            )
        elif sys.argv[1] in ["reboot", "poweroff"]:
            confirm = input(f"Reboot {device['name']}? (Vendor {info['Vendor']} (y/n) ")
        elif sys.argv[1] in ["boot"]:
            confirm = "y"
        else:
            confirm = "n"
        if confirm == "y":
            if sys.argv[1] in ["pxe"]:
                print("Setting 1-time pxe boot.")
                js = {
                    "Boot": {
                        "BootSourceOverrideEnabled": "Once",
                        "BootSourceOverrideMode": "UEFI",
                        "BootSourceOverrideTarget": "Pxe",
                    }
                }
                r = requests.patch(
                    f"https://{bmc_ip}/redfish/v1/Systems/1",
                    json=js,
                    verify=False,
                    auth=bmc_auth,
                )
                print(f"{device['name']} - {r.status_code}")
                print(f"{device['name']} - {r.text}")
            if sys.argv[1] in ["reboot", "poweroff", "pxe"]:
                print(f"BMC IP: {bmc_ip}")
                # Force Off
                print("Forcing Off")
                if info["Vendor"] == "Dell":
                    r = requests.post(
                        f"https://{bmc_ip}/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
                        json={"ResetType": "ForceOff"},
                        verify=False,
                        auth=bmc_auth,
                    )
                elif info["Vendor"] == "Supermicro":
                    r = requests.post(
                        f"https://{bmc_ip}/redfish/v1/Systems/1/Actions/ComputerSystem.Reset",
                        json={"ResetType": "ForceOff"},
                        verify=False,
                        auth=bmc_auth,
                    )
                print(f"{device['name']} - {r.status_code}")
                print(f"{device['name']} - {r.text}")
                print("Waiting 10 seconds...")
                sleep(10)
                # Force On
            if sys.argv[1] in ["boot", "reboot", "pxe"]:
                print(f"{device['name']} - Powering Up")
                try:
                    if info["Vendor"] == "Dell":
                        r = requests.post(
                            f"https://{bmc_ip}/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset",
                            json={"ResetType": "On"},
                            verify=False,
                            auth=bmc_auth,
                        )
                    elif info["Vendor"] == "Supermicro":
                        r = requests.post(
                            f"https://{bmc_ip}/redfish/v1/Systems/1/Actions/ComputerSystem.Reset",
                            json={"ResetType": "On"},
                            verify=False,
                            auth=bmc_auth,
                        )
                    print(f"{device['name']} - {r.status_code}")
                    print(f"{device['name']} - {r.text}")
                except Exception as e:
                    print(f"{device['name']} - {e}")
