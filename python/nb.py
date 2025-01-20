from rich.console import Console
from rich.table import Table
import sys
import os
import requests
from joblib import Parallel, delayed
import json


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

    args = sys.argv
    all_devices = []
    if args[1] not in ["patch", "devices", "details", "detail"]:
        output = Parallel(n_jobs=30, verbose=0, backend="threading")(
            map(delayed(get_device), args)
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
                "K8S CLUSTER",
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
                row.append(None)
                row.append("VM")
                row.append(None)
            else:
                row.append(device["custom_fields"]["bmc_ip4"])
                row.append(device["device_type"]["display"])
                try:
                    row.append(device["parent_device"]["display"])
                except:
                    row.append(None)
            row.append(device["custom_fields"]["k8s_cluster"])
            row.append(device["status"]["value"])
            devices_table.append(row)

        # data = sys.stdin.read()
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
    elif args[1] == "patch":
        patch = json.loads(args[-1])
        for host in range(2, len(args) - 1):
            try:
                print(f"Patching {args[host]} with {args[-1]}")
                device = netbox(
                    path=f"/api/dcim/devices/", params={"name__ic": args[host]}
                ).json()
                id = device["results"][0]["id"]
                result = netbox(
                    method="PATCH", path=f"/api/dcim/devices/{id}/", value=patch
                )
                print(f"{args[host]}: {result.status_code}")
            except:
                print(f"{args[host]}: Error")
    elif args[1] == "devices":
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
    elif "detail" in args[1]:
        d = dict()
        device = get_device(args[2])["results"][0]
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
        ips = netbox(
            path="/api/ipam/ip-addresses/", params={"device_id": device["id"]}
        ).json()
        for ip in ips["results"]:
            if ip["assigned_object"]["display"] not in d["interfaces"]:
                d["interfaces"][ip["assigned_object"]["display"]] = list()
            d["interfaces"][ip["assigned_object"]["display"]].append(f'IP: {ip["address"]}')
        import yaml
        print(yaml.dump(d))
