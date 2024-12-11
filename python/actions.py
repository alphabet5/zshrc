import requests
import os
import json
import sys
from rich.console import Console

console = Console()
from rich.prompt import Prompt
from rich.traceback import install

install(show_locals=True)
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from inspect import currentframe, getframeinfo
from datetime import datetime, timedelta
import requests, zipfile, io
from io import BytesIO
from zipfile import ZipFile
import re
from joblib import Parallel, delayed


def pprint(*args):
    """Prints the given arguments along with the filename and line number."""
    frameinfo = getframeinfo(currentframe().f_back)
    console.print(f"{frameinfo.filename}:{frameinfo.lineno} \n", *args)


def ghe(path, params={}, accept="application/json"):
    """Makes a GET request to the GitHub API."""
    token = os.getenv("GITHUB_TOKEN")
    api_url = os.getenv("GITHUB_API_URL")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if api_url[-1] != "/":
        api_url += "/"
    response = requests.get(api_url + path, headers=headers, params=params)
    return response


def get_repo_jobs(repo_org):
    """Fetches job runs for a specific repository."""
    org, repo = repo_org
    runs = ghe(
        f"repos/{org}/{repo}/actions/runs",
        params={"created": (datetime.now() - timedelta(days=1)).strftime(">%Y-%m-%d")},
    )
    if len(runs.json()["workflow_runs"]) > 0:
        for run in runs.json()["workflow_runs"]:
            logs = ghe(
                f"repos/{org}/{repo}/actions/runs/{run['id']}/logs",
                accept="application/vnd.github.v3+json",
            )
            if logs.status_code == 200:
                myzip = ZipFile(BytesIO(logs.content))
                if not any(["Set up job" in name for name in myzip.namelist()]):
                    print(
                        "No Set up job in logs for", repo, run["name"], myzip.namelist()
                    )
                for name in myzip.namelist():
                    if "Set up job" in name:
                        for line in myzip.read(name).decode("utf-8").splitlines():
                            if "Runner name" in line:
                                print(
                                    repo,
                                    run["name"],
                                    re.match(r".*Runner name: \'(.*)\'", line).group(1),
                                    run["url"],
                                )

                if detailed:
                    log_contents = dict()
                    for name in myzip.namelist():
                        log_contents[name] = myzip.read(name).decode("utf-8")
                    with open(logfile, "a") as f:
                        f.write(
                            json.dumps({"repo": repo, "run": run, "logs": log_contents})
                            + "\n"
                        )


def get_repos(org, path="", accept="application/json", params=dict()):
    """Retrieves a list of repositories for a given organization."""
    token = os.getenv("GITHUB_TOKEN")
    api_url = os.getenv("GITHUB_API_URL")
    if path == "":
        path = f"orgs/{org}/repos"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if api_url[-1] != "/":
        api_url += "/"
    r = requests.get(api_url + path, headers=headers, params=params, timeout=10)
    repo_list = [r["name"] for r in r.json()]
    if "link" in r.headers:
        for link in r.headers["link"].split(","):
            if 'rel="last"' in link:
                print(link)
                last_page = int(re.match(r".*page=(\d+)", link).group(1))
                if last_page > 1:
                    for page in range(2, last_page + 1):
                        params["page"] = page
                        r = requests.get(
                            api_url + path, headers=headers, params=params, timeout=10
                        )
                        repo_list = repo_list + [r["name"] for r in r.json()]
    return repo_list


detailed = False
logfile = None
print(sys.argv)
if sys.argv[1] == "--detailed":
    detailed = True
    try:
        logfile = sys.argv[2]
    except IndexError:
        logfile = "actions.log"
    with open(logfile, "w") as f:
        pass

if __name__ == "__main__":
    organizations = [o["login"] for o in ghe("organizations").json()]
    repos = []
    for organization in organizations:
        repos = repos + [(organization, r) for r in get_repos(organization)]

    outputs = Parallel(n_jobs=20, verbose=0, backend="threading")(
        map(delayed(get_repo_jobs), repos)
    )
