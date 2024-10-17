import requests
import os
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
    frameinfo = getframeinfo(currentframe().f_back)
    console.print(f"{frameinfo.filename}:{frameinfo.lineno} \n", *args)

def ghe(path, params={}, accept="application/json"):
    token = os.getenv("GITHUB_TOKEN")
    api_url = os.getenv("GITHUB_API_URL")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28"
    }
    if api_url[-1] != "/":
        api_url += "/"
    response = requests.get(api_url+path, headers=headers, params=params)
    return response

def get_repo_jobs(repo_org):
    org, repo = repo_org
    runs = ghe(f"repos/{org}/{repo}/actions/runs", params={"created": (datetime.now()-timedelta(days=1)).strftime(">%Y-%m-%d")})
    if len(runs.json()['workflow_runs'])>0:
        for run in runs.json()['workflow_runs']:
            logs = ghe(f"repos/{org}/{repo}/actions/runs/{run['id']}/logs", accept="application/vnd.github.v3+json")
            if logs.status_code == 200:
                myzip = ZipFile(BytesIO(logs.content))
                if not any(['Set up job' in name for name in myzip.namelist()]):
                    print("No Set up job in logs for", repo, run['name'], myzip.namelist())
                for name in myzip.namelist():
                    if 'Set up job' in name:
                        for line in myzip.read(name).decode('utf-8').splitlines():
                            if 'Runner name' in line:
                                print(repo, run['name'], re.match(r'.*Runner name: \'(.*)\'', line).group(1), run['url'])
            else:
                print("Error:", logs.status_code,repo, run['name'])

def get_repos(org, path="", accept="application/json", params={}):
    token = os.getenv("GITHUB_TOKEN")
    api_url = os.getenv("GITHUB_API_URL")
    if path == "":
        path = f"orgs/{org}/repos"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28"
    }
    if api_url[-1] != "/":
        api_url += "/"
    repos = requests.get(api_url+path, headers=headers, params=params)
    repo_list = [r['name'] for r in repos.json()]
    if 'link' in repos.headers:
        for link in repos.headers['link'].split(','):
            if 'rel="last"' in link:
                print(link)
                last_page = int(re.match(r'.*page=(\d+)', link).group(1))
                if last_page > 1:
                    for page in range(2, last_page+1):
                        params["page"] = page
                        repos = requests.get(api_url+path, headers=headers, params=params)
                        repo_list = repo_list + [r['name'] for r in repos.json()]
    return repo_list


if __name__ == "__main__":
    orgs = [o['login'] for o in ghe("organizations").json()]
    repo_list = []
    for org in orgs:
        repo_list = repo_list + [(org, r) for r in get_repos(org)]

    outputs = Parallel(n_jobs=20, verbose=0, backend="threading")(
        map(delayed(get_repo_jobs), repo_list)
    )
