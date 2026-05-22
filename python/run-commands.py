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
import paramiko.channel
from paramiko.agent import AgentRequestHandler
from contextlib import contextmanager, nullcontext


@contextmanager
def _agent_forwarding_on_invoke_shell():
    """Temporarily patch paramiko.Channel.invoke_shell so that an
    auth-agent-req is sent on the channel BEFORE the shell is invoked.
    sshd only injects SSH_AUTH_SOCK into the shell's environment if the
    forwarding request arrives before the shell process is started, so
    requesting it after ConnectHandler returns is too late."""
    original = paramiko.channel.Channel.invoke_shell

    def patched(self, *args, **kwargs):
        try:
            AgentRequestHandler(self)
        except Exception:
            logger.warning("Failed to request SSH agent forwarding: " + traceback.format_exc())
        return original(self, *args, **kwargs)

    paramiko.channel.Channel.invoke_shell = patched
    try:
        yield
    finally:
        paramiko.channel.Channel.invoke_shell = original

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


def connect(host, agent_forwarding=True):
    key_file = os.getenv("SSH_KEY_FILE", "~/.ssh/id_rsa")
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
    cm = _agent_forwarding_on_invoke_shell() if agent_forwarding else nullcontext()
    with cm:
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

def run(var, commands, timing, scripts, local, agent_forwarding=True):
    output = {}
    errors = {}
    simple = ""
    if local:
        for command in commands:
            c = command.replace("$VAR", var)
            if timing > 0:
                out = subprocess.run(
                    c,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timing
                ).stdout
            else:
                out = subprocess.run(
                    c,
                    shell=True,
                    capture_output=True,
                    text=True
                )
            output[c] = try_parse_json(out.stdout)
            errors[c] = out.stderr
            simple=output[c]
        return var, output, errors, simple
    else:
        for retries in range(100):
            try:
                conn = connect(var, agent_forwarding=agent_forwarding)
                logging.info("Connected to " + var)
                for command in commands:
                    if timing > 0:
                        o = conn.send_command_timing(
                            command,
                            read_timeout=0,
                            last_read=timing
                        )
                    else:
                        o = conn.send_command(command, read_timeout=120)
                    output[command] = try_parse_json(o)
                    simple = output[command]
                    logger.info(try_parse_json(o))
                for script_file, script in scripts.items():
                    if timing > 0:
                        o = conn.send_command_timing(
                            "sudo bash <<'EOF'\n" + script + "\nEOF\n\n",
                            strip_command=False,
                            strip_prompt=False,
                            read_timeout=0,
                            last_read=timing
                        )
                    else:
                        o = conn.send_command(
                            "sudo bash <<'EOF'\n" + script + "\nEOF\n\n",
                            read_timeout=120,
                            strip_command=False,
                            strip_prompt=False
                        )
                    output[script] = try_parse_json(o)
                    simple = output[script]
                    logger.info(try_parse_json(o))
                conn.disconnect()
                return var, output, errors, simple
            except NetmikoTimeoutException:
                logging.info(f"Timeout on {var}")
                if retries >= 2:
                    errors["timeout"] = "Timeout after 3 retries"
                    return var, output, errors, simple
                sleep(1)
            except NetMikoAuthenticationException:
                logging.info(
                    f"Authentication error on {var}" + "\n" + traceback.format_exc()
                )
                if retries >= 0:
                    errors["authentication"] = "Authentication error."
                    return var, output, errors, simple
                sleep(5)
            except:
                logging.info(
                    "Unhandled exception on " + var + "\n" + traceback.format_exc()
                )
                try:
                    conn.disconnect()
                except:
                    pass
                if retries >= 0:
                    return var, output, {"traceback": traceback.format_exc()}, 'unknown error'
                sleep(5)


if __name__ == "__main__":

    # Initialize logger
    logger = logging.getLogger(__name__)

    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Run commands in parallel - locally or on a list of hosts."
    )

    # Define positional arguments
    parser.add_argument(
        "vars", nargs="*", help="List of hostnames, IP addresses, or VARs to loop through."
    )

    # Define optional arguments
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        help="Commands to run."
    )
    parser.add_argument(
        "--script",
        action="append",
        default=[],
        help="Optional, path to a script file containing commands to run on the hosts. (will first check zshrc/scripts directory, then current directory)",
    )
    parser.add_argument(
        "--timing",
        type=int,
        default=0,
        help="Optional, use send_command_timing, and read until there is no new output for {timing} seconds. Default is 0, which uses send_command.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run commands locally instead of on remote hosts. Commands ran will replace $VAR with the value of the list of inputs."
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=80,
        help="Number of parallel workers. Default is 80.",
    )
    parser.add_argument(
        "--no-agent-forwarding",
        dest="agent_forwarding",
        action="store_false",
        help="Disable SSH agent forwarding (enabled by default).",
    )
    parser.set_defaults(agent_forwarding=True)

    # Parse arguments
    args = parser.parse_args()

    # Extract parsed values
    vars = args.vars
    commands = args.command
    scripts = {}
    my_dir = os.path.dirname(os.path.abspath(__file__))
    scripts_dir = os.path.join(os.path.dirname(my_dir), 'scripts')
    cwd = os.getcwd()
    for s in args.script:
        if os.path.exists(os.path.join(scripts_dir, s)):
            scripts[os.path.join(scripts_dir, s)] = open(os.path.join(scripts_dir, s)).read()
        elif os.path.exists(os.path.join(cwd, s)):
            scripts['os.path.join(cwd, s)'] = open(os.path.join(cwd, s)).read()
        else:
            logger.error(f"Script {s} not found in scripts directory or current directory.")
            sys.exit(1)
    timing = args.timing
    timing_mode = timing > 0
    logger.info("Hosts: " + str(vars))
    logger.info("Commands: " + str(commands))
    logger.info("Scripts: " + str([s for s in scripts.keys()]))
    logger.info(f"Timing Mode: {timing_mode}")
    logger.info("Giving you a few seconds to cancel..")
    try:
        for s in tqdm(range(5)):
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)
    futures = []
    ex = ThreadPoolExecutor(max_workers=args.parallel)
    for var in vars:
        # host_list.append({"hostname": host})
        futures.append(ex.submit(run, var=var, commands=commands, timing=timing, scripts=scripts, local=args.local, agent_forwarding=args.agent_forwarding))

    for future in futures:
        var, output, errors, simple = future.result()
        print(json.dumps({"name": var, "simple": simple, "output": output, "errors": errors}))
