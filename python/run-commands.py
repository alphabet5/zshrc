import argparse
import json
import time
import os
import traceback
import logging
import sys
import socket
from time import sleep
import subprocess
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm
from netmiko import ConnectHandler
from netmiko.exceptions import NetMikoAuthenticationException, NetmikoTimeoutException
from paramiko.ssh_exception import SSHException
import re
import paramiko.rsakey
import paramiko.ed25519key

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
    for _ in range(3):
        try:
            s.connect((ip, int(port)))
            s.shutdown(2)
            return True
        except:
            pass
    return False


def connect(host):
    key_file = "~/.ssh/id_rsa"
    key_file_expanded = os.path.expanduser(key_file)
    key = paramiko.rsakey.RSAKey(filename=key_file_expanded)
    info = {
        "device_type": "linux",
        "host": host,
        "ssh_config_file": "~/.ssh/config",
        "username": subprocess.run("whoami", stdout=subprocess.PIPE, check=True)
        .stdout.decode("utf-8")
        .strip(),
        "use_keys": True,
        "pkey": key,
        "key_file": key_file,
        "allow_agent": True,
    }
    try:
        conn = ConnectHandler(**info)
    except (NetMikoAuthenticationException, ValueError, SSHException):
        key_file = "~/.ssh/id_ed25519"
        key_file_expanded = os.path.expanduser(key_file)
        key = paramiko.ed25519key.Ed25519Key(filename=key_file_expanded)
        info["pkey"] = key
        conn = ConnectHandler(**info)
    return conn

def try_parse_json(o):
    try:
        if isinstance(o, str):
            o = o.strip()
        if o.startswith("{") or o.startswith("["):
            # Try to parse as JSON, including multiline JSON logs
            try:
                return json.loads(o)
            except json.JSONDecodeError:
                matches = re.findall(r'({.*?}|\[.*?\])', o, re.DOTALL)
                if matches:
                    try:
                        # Return the first valid JSON object found
                        return [json.loads(a) for a in matches]
                    except Exception:
                        pass
                raise
        else:
            return o
    except json.JSONDecodeError:
        return o
    except Exception as e:
        logging.error(f"Error parsing JSON: {e}")
        return o

def run(host, commands, timing):
    output = {}
    for retries in range(100):
        try:
            conn = connect(host)
            logging.info("Connected to " + host)
            for command in commands:
                if timing > 0:
                    o = conn.send_command_timing(
                        command, delay_factor=timing
                    )
                    output[command] = try_parse_json(o)
                else:
                    o = conn.send_command(command, read_timeout=120)
                    output[command] = try_parse_json(o)
            conn.disconnect()
            return host, output
        except NetmikoTimeoutException:
            logging.info(f"Timeout on {host}")
            if retries >= 2:
                return host, "timeout"
            sleep(1)
        except NetMikoAuthenticationException:
            logging.info(
                f"Authentication error on {host}" + "\n" + traceback.format_exc()
            )
            if retries >= 0:
                return host, "auth"
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
            sleep(5)


if __name__ == "__main__":

    # Initialize logger
    logger = logging.getLogger(__name__)

    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Run commands on multiple hosts with optional timing delay."
    )

    # Define positional arguments
    parser.add_argument(
        "hosts", nargs="*", help="List of hostnames or IP addresses to connect to."
    )

    # Define optional arguments
    parser.add_argument(
        "--command", nargs="+", help="Commands to run on the specified hosts."
    )
    parser.add_argument(
        "--timing",
        type=int,
        default=0,
        help="Optional, set the delay_factor, and run commands with send_command_timing.",
    )

    # Parse arguments
    args = parser.parse_args()

    # Extract parsed values
    hosts = args.hosts
    commands = args.command if args.command else []
    timing = args.timing
    timing_mode = timing > 0
    logger.info("Hosts: " + str(hosts))
    logger.info("Commands: " + str(commands))
    logger.info(f"Timing Mode: {timing_mode}")
    logger.info("Giving you a few seconds to cancel..")
    try:
        for s in tqdm(range(5)):
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)
    futures = []
    ex = ThreadPoolExecutor(max_workers=80)
    for host in hosts:
        # host_list.append({"hostname": host})
        futures.append(ex.submit(run, host=host, commands=commands, timing=timing))

    for future in futures:
        hostname, output = future.result()
        print(json.dumps({"name": hostname, "output": output}))
