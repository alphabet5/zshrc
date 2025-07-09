from rich.console import Console
from rich.table import Table
import sys
import os
import requests
from joblib import Parallel, delayed
import json
import ipaddress
import re
import logging
from pandas import DataFrame as df
import argparse

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

def netbox(method="GET", path="", params={}, value=None):
    nb_url = os.getenv("NETBOX_URL")
    nb_token = os.getenv("NETBOX_TOKEN")
    nb_headers = {"Authorization": f"Token {nb_token}", "Accept": "application/json"}
    if "http" == path[:4]:
        full_url = path
    else:
        full_url = f"{nb_url}/{path}"
    if method == "GET":
        return requests.get(full_url, headers=nb_headers, params=params)
    elif method == "PATCH":
        return requests.patch(
            full_url, headers=nb_headers, params=params, json=value
        )
    elif method == "DELETE":
        return requests.delete(full_url, headers=nb_headers)
    elif method == "POST":
        nb_headers["Content-Type"] = "application/json"
        return requests.post(full_url, headers=nb_headers, json=value)
    else:
        return None


def get_device(name):
    params = {"name__ic": name}
    devices = netbox(path="/api/dcim/devices/", params=params).json()
    try:
        if devices["count"] == 0:
            devices = netbox(
                path="/api/virtualization/virtual-machines/", params=params
            ).json()
    except:
        print(f"Error getting device: {name}")
        print(devices)
    return devices


if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Netbox interface."
    )

    parser.add_argument(
        "action",
        help="Action to perform: get, patch, devices.",
        nargs="?",
    )

    # Define positional arguments
    parser.add_argument(
        "vars", nargs="*", help="Hosts to fetch."
    )

    parser.add_argument(
        "--patch",
        default="",
        help="Json patch to apply to device configurations in netbox.",
    )

    parser.add_argument(
        "--tsv",
        action="store_true",
        help="Output to tsv instead of table format."
    )

    args = parser.parse_args()

    valid_actions = ["patch", "devices", "detail", "details"]
    if args.action not in valid_actions:
        args.vars = [args.action] + args.vars
        args.action = "get"

    all_devices = []
    if args.action == "get":
        output = Parallel(n_jobs=30, verbose=0, backend="threading")(
            map(delayed(get_device), args.vars)
        )

        for devices in output:
            if devices["count"] > 0:
                all_devices += devices["results"]
        devices_table = [
            [
                "NAME",
                "ENV",
                "PURPOSE",
                "PLATFORM",
                "BMC",
                "MODEL",
                "PARENT",
                "BAY",
                "SWITCH",
                "INTERFACE",
                "K8S-CLUSTER",
                "STATUS",
            ]
        ]
        for device in all_devices:
            row = list()
            row.append(device["name"])
            row.append(device["custom_fields"]["environment"])
            row.append(device["custom_fields"]["purpose"])
            try:
                row.append(device["platform"]["name"])
            except:
                row.append(None)
            if "virtualization" in device["url"]:
                row.append(None) # model
                row.append("VM")
                row.append(None) # bay
                row.append(None) # switch
                row.append(None) # interface
            else:
                bmc_ok = False
                try:
                    bmc_ok = bool(
                        ipaddress.ip_address(device["custom_fields"]["bmc_ip4"])
                    )
                    bmc_ip = device["custom_fields"]["bmc_ip4"]
                except:
                    # try to get bmc ip from "mgmt" interface
                    print(f"BMC ip not found in custom fields for {device['name']}, trying to get from netbox.")
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
                row.append(bmc_ip)
                row.append(device["device_type"]["display"])
                try:
                    row.append(device["parent_device"]["display"])
                except:
                    row.append(None)
                try:
                    row.append(device["parent_device"]["device_bay"]["display"])
                except:
                    row.append(None)
                try:
                    found_ints = False
                    interfaces = netbox(path="/api/dcim/interfaces/", params={"device_id": device['id']}).json()
                    for interface in interfaces["results"]:
                        if interface["name"].lower() in ["lan0", "eno1"]:
                            switchname = interface["connected_endpoints"][0]["device"]["name"]
                            switchint = interface["connected_endpoints"][0]["name"]
                            row.append(switchname)
                            row.append(switchint)
                            found_ints = True
                            break
                    if not found_ints:
                        row.append(None)
                        row.append(None)
                except:
                    logger.error(f"Error getting interfaces for {device['name']}")
                    row.append(None)
                    row.append(None)
            row.append(device["custom_fields"]["k8s_cluster"])
            row.append(device["status"]["value"])
            devices_table.append(row)
        if args.tsv:
            o = df(devices_table[1:], columns=devices_table[0])
            o.to_csv(sys.stdout, sep="\t", index=False, header=True)
        else:
            table = Table(
                box=None,
            )
            header = False
            for row in devices_table:
                if not header:
                    for col in row:
                        table.add_column(col)
                    header = True
                else:
                    table.add_row(*row)
            console = Console()
            console.print(table)
    elif args.action == "patch":
        patch = json.loads(args.patch)
        for host in args.vars:
            try:
                print(f"Patching {host} with {args.patch}")
                try:
                    device = netbox(
                        path=f"/api/dcim/devices/", params={"name__ic": host}
                    ).json()
                    id = device["results"][0]["id"]
                    result = netbox(
                        method="PATCH", path=f"/api/dcim/devices/{id}/", value=patch
                    )
                except:
                    device = netbox(
                        path=f"/api/virtualization/virtual-machines/",
                        params={"name__ic": host},
                    ).json()
                    id = device["results"][0]["id"]
                    result = netbox(
                        method="PATCH",
                        path=f"/api/virtualization/virtual-machines/{id}/",
                        value=patch,
                    )
                if result.status_code == 200:
                    print(f"{host}: {result.status_code}")
                else:
                    print(f"{host}: {result.status_code} - {result.text}")
            except:
                print(f"{host}: Error")
    elif args.action == "devices":
        all_devices = []
        devices = netbox(path="/api/dcim/devices/", params={"limit": 10000}).json()
        all_devices = all_devices + devices["results"]
        while devices["next"] is not None:
            devices = netbox(path=devices["next"]).json()
            all_devices = all_devices + devices["results"]
        virtual_machines = netbox(
            path="/api/virtualization/virtual-machines/", params={"limit": 1000}
        ).json()
        all_devices = all_devices + virtual_machines["results"]
        while virtual_machines["next"] is not None:
            virtual_machines = netbox(path=virtual_machines["next"]).json()
            all_devices = all_devices + virtual_machines["results"]
        print(json.dumps(all_devices, indent=4))
    elif args.action in ["detail", "details"]:
        for host in args.vars:
            d = dict()
            device = get_device(host)["results"][0]
            d["name"] = device["name"]
            d["status"] = device["status"]["value"]
            d["role"] = device["role"]["display"]
            d["platform"] = device["platform"]["name"]
            d["model"] = device["device_type"]["display"]
            d["bmc"] = device["custom_fields"]["bmc_ip4"]
            try:
                d["parent"] = device["parent_device"]["display"]
            except:
                pass
            d["k8s_cluster"] = device["custom_fields"]["k8s_cluster"]
            d["environment"] = device["custom_fields"]["environment"]
            d["purpose"] = device["custom_fields"]["purpose"]
            interfaces = netbox(
                path="/api/dcim/interfaces/", params={"device_id": device["id"]}
            ).json()
            d["interfaces"] = dict()
            for interface in interfaces["results"]:
                if interface["name"] not in d["interfaces"]:
                    d["interfaces"][interface["name"]] = list()
                try:
                    d["interfaces"][interface["name"]].append(f"Switch: {interface['connected_endpoints'][0]['device']['name']} {interface['connected_endpoints'][0]['name']}")
                except:
                    pass
                try:
                    if "vlans" not in d["interfaces"]:
                        d["interfaces"]["vlans"] = dict()
                    d["interfaces"]["vlans"][interface["name"]] = f"{[v["vid"] for v in interface['tagged_vlans']]}"
                except:
                    pass
            ips = netbox(
                path="/api/ipam/ip-addresses/", params={"device_id": device["id"]}
            ).json()
            for ip in ips["results"]:
                if ip["assigned_object"]["display"] not in d["interfaces"]:
                    d["interfaces"][ip["assigned_object"]["display"]] = list()
                d["interfaces"][ip["assigned_object"]["display"]].append(f'IP: {ip["address"]}')
            import yaml
            print("---")
            print(yaml.dump(d))
