import argparse
import json

# from joblib import Parallel, delayed
import traceback
import netmiko.exceptions
import logging
import sys
import socket
from time import sleep
import re
import subprocess
import yaml
import gunicorn
from threading import Timer
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import subprocess
import time
import datetime
import logging
import sys
import re
import traceback
import os
import sys
from tqdm import tqdm

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


def is_open(ip, port, timeout=5):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    for retries in range(3):
        try:
            s.connect((ip, int(port)))
            s.shutdown(2)
            return True
        except:
            pass
    return False


def connect(host):
    from netmiko import ConnectHandler
    import paramiko.rsakey
    import paramiko.ed25519key
    import os
    import re

    key_file = "~/.ssh/id_rsa"
    key_file_expanded = os.path.expanduser(key_file)
    key = paramiko.rsakey.RSAKey(filename=key_file_expanded)
    info = {
        "device_type": "linux",
        "host": host,
        "ssh_config_file": "~/.ssh/config",
        "username": subprocess.run("whoami", stdout=subprocess.PIPE)
        .stdout.decode("utf-8")
        .strip(),
        "use_keys": True,
        "pkey": key,
        "key_file": key_file,
        "allow_agent": True,
    }
    try:
        conn = ConnectHandler(**info)
    except netmiko.exceptions.NetMikoAuthenticationException:
        key_file = "~/.ssh/id_ed25519"
        key_file_expanded = os.path.expanduser(key_file)
        key = paramiko.ed25519key.Ed25519Key(filename=key_file_expanded)
        info["pkey"] = key
        conn = ConnectHandler(**info)
    return conn


def run(host, commands):
    output = dict()
    for retries in range(100):
        try:
            conn = connect(host)
            logging.info("Connected to " + host)
            for command in commands:
                output[command] = conn.send_command(command, read_timeout=120)
            conn.disconnect()
            return host, output
        except netmiko.exceptions.NetMikoTimeoutException:
            logging.info(f"Timeout on {host}")
            if retries >= 2:
                return host, "timeout"
            else:
                sleep(1)
        except netmiko.exceptions.NetMikoAuthenticationException:
            logging.info(
                f"Authentication error on {host}" + "\n" + traceback.format_exc()
            )
            if retries >= 0:
                return host, "auth"
            else:
                sleep(5)
        except:
            logging.info(
                "Unhandled exception on " + host + "\n" + traceback.format_exc()
            )
            try:
                conn.disconnect()
            except:
                pass
            if retries >= 0:
                return host, traceback.format_exc()
            else:
                sleep(5)


if __name__ == "__main__":
    args = sys.argv
    hosts = list()
    commands = list()
    is_command = False
    for arg in args[1:]:
        if arg == "--command":
            is_command = True
        if arg != "--command":
            if not is_command:
                hosts.append(arg)
            else:
                commands.append(arg)
        if arg in ["help", "--help", "?", "-h", "--h"]:
            print("Usage\nrun-commands [host] [host] --command 'your command'")
            sys.exit(0)
    logger.info("Hosts: " + str(hosts))
    logger.info("Commands: " + str(commands))
    logger.info("Giving you a few seconds to cancel..")
    try:
        for s in tqdm(range(5)):
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)
    futures = list()
    ex = ThreadPoolExecutor(max_workers=80)
    for host in hosts:
        # host_list.append({"hostname": host})
        futures.append(ex.submit(run, host=host, commands=commands))

    for future in futures:
        hostname, output = future.result()
        print(json.dumps({"name": hostname, "output": output}))
