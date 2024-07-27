from datetime import date, datetime, timedelta
from jira import JIRA
import yaml
import os
import sys

jira = JIRA(
    server=os.getenv("JIRA_SERVER"),
    basic_auth=(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN")),
)

if sys.argv[1][0] == "h" or sys.argv[1][0] == "?":
    print(
        """j [command] [arg]
examples:
jira c summary [description] - create a "needs review" jira description is optional
jira ci summary [description] - create an "in progress" jira
jira cd summary [description] - create a "done" jira
jira s searchterm - search for a recent jira
jira standup - displays previously closed tickets and current in-progress tickets for standup notes\n"""
    )

try:
    desc = sys.argv[3]
except:
    desc = ""
try:
    f = {
        "project": {"key": os.getenv("JIRA_PROJECT")},
        "summary": sys.argv[2],
        "description": desc,
        "issuetype": {"name": "Task"},
        "customfield_10022": 0.5,
    }
except:
    pass
# create, default, needs review
if sys.argv[1] == "c":
    result = jira.create_issue(fields=f)
    print(result.key)
# ci for create, in-progress
if sys.argv[1] == "ci":
    result = jira.create_issue(fields=f)
    print(result.key)
    jira.transition_issue(result, transition="In progress")

# create, done
if sys.argv[1] == "cd":
    result = jira.create_issue(fields=f)
    print(result.key)
    jira.transition_issue(result, transition="In progress")
    jira.transition_issue(result, transition="For Review")

if sys.argv[1] == "s":
    result = jira.search_issues('created >=-5w AND summary ~ "' + sys.argv[2] + '*"')
    for i in result:
        print(i.key, " - ", i.fields.created, " - ", i.fields.summary)

if sys.argv[1] == "standup":
    current_day = datetime.now().weekday()
    t = date.today()
    if current_day == 0:
        # if monday, check from friday
        daysAgo = -3
    else:
        daysAgo = -1

    resolved = jira.search_issues(
        f"project = {os.getenv('JIRA_PROJECT')} and assignee = currentUser() and resolutiondate >=  startOfDay({daysAgo})",
        maxResults=100,
    )
    inprogress = jira.search_issues(
        f"project = {os.getenv('JIRA_PROJECT')} and assignee = currentUser() and status not in (Done, Closed, Backlog)",
        maxResults=100,
    )
    out = {"yesterday": [], "today": []}
    for i in resolved:
        out["yesterday"].append((i.raw["key"] + " - " + i.raw["fields"]["summary"]))
    for i in inprogress:
        if i.raw["fields"]["status"]["name"] == "In progress":
            out["today"].append((i.raw["key"] + " - " + i.raw["fields"]["summary"]))
    print(yaml.dump(out, sort_keys=False))
