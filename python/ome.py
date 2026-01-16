#!/usr/bin/env python3
import argparse
import sys
import time
import warnings
import requests
import os
import re
from datetime import timedelta
from datetime import datetime
import logging

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ---- simple helper: fail fast with message ----
def die(msg, code=1):
    logger.error(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

# ---- API helpers ----
def login(ome, user, pwd, verify=True):
    url = f"{ome}/api/SessionService/Sessions"
    r = requests.post(url, json={"UserName": user, "Password": pwd, "SessionType": "API"}, verify=verify)
    if r.status_code not in (200, 201):
        die(f"Login failed ({r.status_code}): {r.text}")
    token = r.headers.get("X-Auth-Token")
    if not token:
        die("Login failed: missing X-Auth-Token")
    return {"X-Auth-Token": token, "Content-Type": "application/json"}

def api_get(ome, headers, path, verify=True):
    r = requests.get(f"{ome}{path}", headers=headers, verify=verify)
    if r.status_code != 200:
        die(f"GET {path} failed ({r.status_code}): {r.text}")
    return r.json()

def api_post(ome, headers, path, payload, verify=True):
    r = requests.post(f"{ome}{path}", headers=headers, json=payload, verify=verify)
    if r.status_code not in (200, 201):
        try:
            j = r.json()
            ext = j.get("error", {}).get("@Message.ExtendedInfo", [])
            hint = "; ".join(f"{e.get('MessageId')}: {e.get('Message')}" for e in ext if isinstance(e, dict)) or r.text
        except Exception:
            hint = r.text
        die(f"POST {path} failed ({r.status_code}): {hint}")
    return r.json()

# ---- core steps ----
def find_device_by_name(ome, headers, nodename, verify=True):
    path = f"/api/DeviceService/Devices?$filter=DeviceName eq '{nodename}'"
    data = api_get(ome, headers, path, verify)
    devices = data.get("value", [])
    if len(devices) != 1:
        die(f"Expected 1 device named '{nodename}', found {len(devices)}")
    dev = devices[0]
    return dev["Id"], dev.get("Model", "")

def select_baseline(ome, headers, device_model, baseline_name=None, verify=True):
    """Fast match: exact name if provided, else compare the model code (e.g., FC640)."""
    data = api_get(ome, headers, "/api/UpdateService/Baselines", verify)
    bls = data.get("value", [])
    if not bls:
        die("No baselines found in OME.")

    if baseline_name:
        for b in bls:
            if (b.get("Name") or "").strip().lower() == baseline_name.strip().lower():
                return {"Id": b["Id"], "Name": b.get("Name"),
                        "CatalogId": b.get("CatalogId"), "RepositoryId": b.get("RepositoryId")}
        die(f"Baseline named '{baseline_name}' not found.")

    # Extract concise model code: FC640, R750, MX750c, etc.
    cleaned = re.sub(r"\b(Dell|EMC|Dell\s*EMC|Power\s*Edge|PowerEdge)\b", "", device_model or "", flags=re.I).strip()
    m = re.findall(r"[A-Za-z]{1,3}\d{3,4}[A-Za-z]?", cleaned)
    dev_code = (m and max((t.upper() for t in m), key=len)) or cleaned.upper()

    # Exact code match first, then contains
    for b in bls:
        name = (b.get("Name") or "").upper()
        if name == dev_code:
            return {"Id": b["Id"], "Name": b.get("Name"),
                    "CatalogId": b.get("CatalogId"), "RepositoryId": b.get("RepositoryId")}
    for b in bls:
        name = (b.get("Name") or "").upper()
        if dev_code in name or name in dev_code:
            return {"Id": b["Id"], "Name": b.get("Name"),
                    "CatalogId": b.get("CatalogId"), "RepositoryId": b.get("RepositoryId")}

    die(f"No baseline matched device model '{device_model}'. Try --baseline-name.")

def get_baselines_for_device(ome, headers, device_id, verify=True):
    """
    Returns the baselines associated with a device.
    Primary payload key is 'DeviceIds'. If that 400s on older builds,
    we fall back to 'Ids'.
    """
    # try the canonical payload
    try:
        return api_post(
            ome, headers,
            "/api/UpdateService/Actions/UpdateService.GetBaselinesForDevices",
            {"DeviceIds": [int(device_id)]},
            verify
        ) or []
    except SystemExit as e:
        # If we see "invalid property DeviceIds", retry with 'Ids'
        msg = str(e)
        if "invalid property DeviceIds" in msg:
            return api_post(
                ome, headers,
                "/api/UpdateService/Actions/UpdateService.GetBaselinesForDevices",
                {"Ids": [int(device_id)]},
                verify
            ) or []
        raise

def is_device_in_baseline(ome, headers, baseline_id, device_id, verify=True):
    bls = get_baselines_for_device(ome, headers, device_id, verify)
    # API may return a list or an object with 'value'
    items = bls if isinstance(bls, list) else (bls.get("value") or [])
    return any(int(b.get("Id", -1)) == int(baseline_id) for b in items)

def poll_job(ome, headers, job_id, verify=True, interval=10):
    path = f"/api/JobService/Jobs({job_id})"
    lrname = "NotRun"
    start_time = time.time()
    while lrname in ["NotRun", "Running"]:
        data = api_get(ome, headers, path, verify)
        js = data.get("JobStatus", {})
        lr = data.get("LastRunStatus", {})
        sid = js.get("Id")
        sname = js.get("Name")
        lrname = lr.get("Name")
        logger.info(f"Job {job_id}: Status={sid}/{sname} LastRun={lrname}")
        if lrname not in ["NotRun", "Running"]:
            logger.info(f"Time taken: {timedelta(seconds=(time.time() - start_time))}")
            return sid, sname, lrname, data
        time.sleep(interval)

def find_active_job_for_device(ome, headers, device_id, verify=True, max_scan=200, only_update_tasks=True):
    """
    Walks the Jobs collection (following @odata.nextLink) and returns the first
    non-terminal job that targets this device. Optionally restricts to Update_Task jobs.
    """
    non_terminal = {2020, 2030, 2040, 2050, 2065, 2080, 2090}  # queued/running-ish statuses
    scanned = 0
    path = "/api/JobService/Jobs"   # no $orderby/$top — some OME builds 501 on those

    while path and scanned < max_scan:
        data = api_get(ome, headers, path, verify)
        jobs = data.get("value", [])
        for j in jobs:
            scanned += 1
            if scanned > max_scan:
                break

            # (optional) consider only firmware update tasks
            if only_update_tasks:
                jt = (j.get("JobType") or {}).get("Id")
                jtn = (j.get("JobType") or {}).get("Name", "")
                if jt not in (5, None) and "update" not in (jtn or "").lower():
                    continue

            js = (j.get("JobStatus") or {}).get("Id")
            if js in non_terminal:
                jid = j.get("Id")
                if not jid:
                    continue
                # Check Targets on the job detail (list payload may not include Targets)
                detail = api_get(ome, headers, f"/api/JobService/Jobs({jid})", verify)
                for t in (detail.get("Targets") or []):
                    try:
                        if int(t.get("Id", -1)) == int(device_id):
                            return jid
                    except (TypeError, ValueError):
                        continue

        # follow server-provided pagination if available
        next_link = data.get("@odata.nextLink")
        if next_link:
            # next_link may be absolute or relative; normalize to a path
            if next_link.startswith("http"):
                # strip base URL part if present
                if next_link.lower().startswith(ome.lower()):
                    path = next_link[len(ome):]
                else:
                    # cross-host nextLink shouldn’t happen; fall back to absolute GET
                    path = next_link  # api_get handles absolute too if you prefer; else use requests directly
            else:
                path = next_link
        else:
            path = None

    return None

def create_update_job(ome, headers, device_id, repo_id, catalog_id, baseline_id, src_names, nodename, verify=True):
    payload = {
        "Id": 0,
        "JobName": f"Update Firmware ({nodename})",
        "JobDescription": "Firmware Update via API",
        "Schedule": "startNow",
        "State": "Enabled",
        "JobType": {"Id": 5, "Name": "Update_Task"},
        "Params": [
            {"Key": "complianceReportId", "Value": str(baseline_id)},
            {"Key": "repositoryId", "Value": str(repo_id)},
            {"Key": "catalogId", "Value": str(catalog_id)},
            {"Key": "operationName", "Value": "INSTALL_FIRMWARE"},
            {"Key": "complianceUpdate", "Value": "true"},
            {"Key": "signVerify", "Value": "true"},
            {"Key": "stagingValue", "Value": "false"},
        ],
        "Targets": [{
            "Id": int(device_id),
            "Data": ";".join(src_names),
            "TargetType": {"Id": 1000, "Name": "DEVICE"}
        }]
    }
    resp = api_post(ome, headers, "/api/JobService/Jobs", payload, verify)
    jid = resp.get("Id")
    if not jid: die(f"Job creation returned no Id: {resp}")
    return jid

# def components_from_baseline(ome, headers, baseline_id, device_id, verify=True):
#     """
#     Read component compliance for a device from the baseline via GET, avoiding the
#     GetBaselinesReportByDeviceids action (which varies between OME builds).
#     """
#     def normalize_next(path_or_url):
#         if not path_or_url:
#             return None
#         if path_or_url.startswith("http"):
#             return path_or_url[len(ome):] if path_or_url.lower().startswith(ome.lower()) else path_or_url
#         return path_or_url

#     path = f"/api/UpdateService/Baselines({int(baseline_id)})/DeviceComplianceReports"
#     all_dev_reports = []

#     while path:
#         data = api_get(ome, headers, path, verify)
#         all_dev_reports.extend(data.get("value") or data.get("DeviceComplianceReports") or [])
#         path = normalize_next(data.get("@odata.nextLink"))

#     comps = []
#     for devrep in all_dev_reports:
#         try:
#             if int(devrep.get("DeviceId", -1)) != int(device_id):
#                 continue
#         except (TypeError, ValueError):
#             continue
#         for c in (devrep.get("ComponentComplianceReports") or []):
#             status = (c.get("ComplianceStatus") or "").upper()
#             action = (c.get("UpdateAction") or "").upper()
#             src = c.get("SourceName")
#             if src and (status not in ("COMPLIANT", "OK") or action == "UPGRADE"):
#                 comps.append(src)
#         break  # found our device report; no need to keep scanning

#     return comps

def components_from_baseline(ome, headers, baseline_id, device_id, verify=True, reboot=False):
    """
    Read component compliance for a device from the baseline via GET, avoiding the
    GetBaselinesReportByDeviceids action (which varies between OME builds).

    Parameters
    ----------
    ome : str
        Base URL for the OME instance (e.g., "https://ome.example.com").
    headers : dict
        HTTP headers including authentication.
    baseline_id : int
        The baseline identifier.
    device_id : int
        The device identifier.
    verify : bool, optional
        Whether to verify SSL certificates. Defaults to True.
    reboot : bool, optional
        If True, trigger a device reboot when non-compliant components are detected.
        Defaults to False.

    Returns
    -------
    list[str]
        Names of components that are non-compliant or require upgrade.
    """
    def normalize_next(path_or_url):
        if not path_or_url:
            return None
        if path_or_url.startswith("http"):
            return path_or_url[len(ome):] if path_or_url.lower().startswith(ome.lower()) else path_or_url
        return path_or_url

    path = f"/api/UpdateService/Baselines({int(baseline_id)})/DeviceComplianceReports"
    all_dev_reports = []

    while path:
        data = api_get(ome, headers, path, verify)
        all_dev_reports.extend(data.get("value") or data.get("DeviceComplianceReports") or [])
        path = normalize_next(data.get("@odata.nextLink"))

    comps = []
    for devrep in all_dev_reports:
        try:
            if int(devrep.get("DeviceId", -1)) != int(device_id):
                continue
        except (TypeError, ValueError):
            continue
        for c in (devrep.get("ComponentComplianceReports") or []):
            status = (c.get("ComplianceStatus") or "").upper()
            action = (c.get("UpdateAction") or "").upper()
            src = c.get("SourceName")
            if src and (status not in ("COMPLIANT", "OK") or action == "UPGRADE"):
                comps.append(src)
        break  # found our device report; no need to keep scanning

    # If requested, reboot the device when there are components that need action.
    if reboot and comps:
        # OpenManage Enterprise DeviceService reboot action supports multiple IDs;
        # we pass a single device here.
        reboot_path = "/api/DeviceService/Actions/DeviceService.Reboot"
        reboot_payload = {"DeviceIds": [int(device_id)]}
        try:
            resp = api_post(ome, headers, reboot_path, reboot_payload, verify=verify)
            # Optional: surface some lightweight feedback for callers/logs
            # (api_post already raises/dies on non-200/201)
            print(f"Reboot requested for device {device_id}: {resp}")
        except Exception as e:
            # Do not change the return type; just report the failure
            print(f"Failed to trigger reboot for device {device_id}: {e}")

    return comps

# ---- main ----
def main():
    p = argparse.ArgumentParser(description="Schedule OME firmware updates for a device and follow the job.")
    p.add_argument("--ome", required=False, help="OME base URL, e.g. https://ome.company.local", default=os.getenv('OME_HOSTNAME'))
    p.add_argument("--user", required=False, help="OME username", default=os.getenv('OME_USERNAME'))
    p.add_argument("--password", required=False, help="OME password", default=os.getenv('OME_PASSWORD'))
    p.add_argument("--nodename", required=True, help="Exact device name as shown in OME")
    p.add_argument("--baseline-name", help="Exact baseline name (optional). If omitted, auto-match by device model.")
    p.add_argument("--insecure", action="store_true", help="Disable TLS verification (self-signed certs)")
    p.add_argument("--poll", type=int, default=10, help="Polling interval seconds (default: 10)")
    p.add_argument("--reboot", action="store_true", help="Automatically reboot if required. Default=false")
    args = p.parse_args()

    reboot = args.reboot
    verify = not args.insecure
    if args.insecure:
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    headers = login(args.ome, args.user, args.password, verify)
    logger.info("Authenticated.")

    device_id, model = find_device_by_name(args.ome, headers, args.nodename, verify)
    logger.info(f"Device: id={device_id} model='{model}'")

    existing_job = find_active_job_for_device(args.ome, headers, device_id, verify)
    if existing_job:
        logger.info(f"Found existing active job for this device: {existing_job}")
        sid, sname, lrname, _ = poll_job(args.ome, headers, existing_job, verify, interval=args.poll)
        logger.info("\nFinal:")
        logger.info(f"  JobId: {existing_job}")
        logger.info(f"  JobStatus: {sid}/{sname}")
        logger.info(f"  LastRunStatus: {lrname}")
        if lrname not in ["Warning"]:
            sys.exit(0 if sid == 2060 else 2)

    bl = select_baseline(args.ome, headers, model, baseline_name=args.baseline_name, verify=verify)
    logger.info(f"Baseline: id={bl['Id']} name='{bl['Name']}' repo={bl['RepositoryId']} catalog={bl['CatalogId']}")

    # NEW: ensure the device is associated with this baseline
    if not is_device_in_baseline(args.ome, headers, bl["Id"], device_id, verify):
        die(f"Device {device_id} is not associated with baseline '{bl['Name']}' (Id {bl['Id']}). "
            f"Associate it in OME and retry.")
    
    comps = components_from_baseline(args.ome, headers, bl["Id"], device_id, verify, reboot=reboot)

    if not comps:
        logger.info("host is already up to date")
        sys.exit(0)

    logger.info(f"Components to update ({len(comps)}):")
    for c in comps:
        logger.info(f"  - {c}")

    job_id = create_update_job(args.ome, headers, device_id, bl["RepositoryId"], bl["CatalogId"], bl["Id"], comps, args.nodename, verify)
    logger.info(f"Created job: {job_id}")

    sid, sname, lrname, _ = poll_job(args.ome, headers, job_id, verify, interval=args.poll)
    logger.info("\nFinal:")
    logger.info(f"  JobId: {job_id}")
    logger.info(f"  JobStatus: {sid}/{sname}")
    logger.info(f"  LastRunStatus: {lrname}")
    sys.exit(0 if sid == 2060 else 2)

if __name__ == "__main__":
    main()
