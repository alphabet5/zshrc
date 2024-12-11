import requests
import re
import logging
from datetime import datetime, timezone, timedelta
from joblib import Parallel, delayed

logger = logging.getLogger(__name__)

# alertmanager openapi spec can be found here:
# https://github.com/prometheus/alertmanager/blob/main/api/v2/openapi.yaml
# You can use https://editor.swagger.io/ for a better view.


def matcher_to_str(matcher):
    """
    "matcher" is a dict that alertmanager uses to match silences to alerts.
    It follows the prometheus format of key=value / key=~value.*
    {
    "matchers": [
        {
        "name": "alertname",
        "value": ".*",
        "isRegex": true,
        "isEqual": true
        }
    ]
    }
    this is equivalent to alertname=~".*"
    """
    sign = ""
    if matcher["isEqual"]:
        sign += "="
    else:
        sign += "!"
    if matcher["isRegex"]:
        sign += "~"
    return f"{matcher['name']}{sign}\"{matcher['value']}\""


def str_to_matchers(filter_str):
    """
    Convert a string of filters to a list of matchers.
    The filters should be the prometheus/alertmanager format of key=value / key=~value.*
    """
    matchers = []
    for filter in filter_str.split(","):
        match = re.match(r'([0-9a-zA-Z_-]+)(=|=~|!=|!~)"(.+)"', filter)
        isRegex = bool("~" in match.group(2))
        isEqual = bool("=" in match.group(2))
        matchers.append(
            {
                "name": match.group(1),
                "isEqual": isEqual,
                "isRegex": isRegex,
                "value": match.group(3),
            }
        )
    return matchers


def ts_to_human(ts):
    """
    Convert a timestamp to a human readable string of how far in the future it is.
    """
    timestamp = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
    timestamp = timestamp.replace(tzinfo=timezone.utc)
    secs = (timestamp - datetime.now(timezone.utc)).total_seconds()
    if secs < 0:
        secs = 0 - secs
    if secs > (2 * 24 * 60 * 60):
        return f"{int(secs / (24 * 60 * 60))}d"
    elif secs > (60 * 60):
        return f"{int(secs / (60*60))}h"
    else:
        return f"{int(secs / 60)}m"


def human_to_ts(human):
    match = re.match(r"(\d+)([dhm]?)", human)
    if match.group(2) in ["m", ""]:
        delta = timedelta(minutes=int(match.group(1)))
    elif match.group(2) == "h":
        delta = timedelta(hours=int(match.group(1)))
    elif match.group(2) == "d":
        delta = timedelta(days=int(match.group(1)))
    else:
        raise ValueError(f"Couldn't parse duration: {human}")
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%S.%f")[
        :-3
    ] + "Z"


def get_silences(alertmanager):
    all_silences = dict()
    url = f"https://{alertmanager}/api/v2/silences"
    params = {"state": "active"}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        silences = response.json()
        all_silences[alertmanager] = silences
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting shutups from {alertmanager}: {e}")
    return all_silences


def silence_summary(alertmanagers):
    """
    Lists all defined silences and formats them for slack.
    """
    all_silences = dict()
    all_silences_list = Parallel(n_jobs=10, verbose=0, backend="threading")(
        map(delayed(get_silences), alertmanagers)
    )
    for silence in all_silences_list:
        all_silences.update(silence)
    output = ""
    expired = 0
    for instance, silences in all_silences.items():
        for silence in silences:
            filters = ""
            for matcher in silence["matchers"]:
                filters += f"{matcher_to_str(matcher)},"
            filters.strip(",")
            if len(filters) > 40:
                filters = filters[:40] + "..."
            if datetime.now(timezone.utc) < datetime.strptime(
                silence["endsAt"], "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=timezone.utc):
                output += f"- {instance} {filters} expires: {ts_to_human(silence['endsAt'])} added: {ts_to_human(silence['updatedAt'])} by: {silence['createdBy']} comment: {silence['comment']}\n"
            else:
                expired += 1
    if expired > 0:
        output += f"\n{expired} silences expired."
    if len(all_silences) > 0:
        return output
    else:
        return "No silences found."


def delete_cmd(info):
    # info format {"instance": instance, "id": id, "filters": filters}
    output = ""
    try:
        response = requests.delete(
            f"https://{info['instance']}/api/v2/silence/{info['id']}"
        )
        response.raise_for_status()
        if len(info["filters"]) > 40:
            info["filters"] = info["filters"][:40] + "..."
        output += f"Deleted silence {amlookup[info['instance']]} {info['filters']} by: {info['createdBy']} comment: {info['comment']}"
    except requests.exceptions.RequestException as e:
        output += f"Error deleting alert from {amlookup[info['instance']]} {info['filters']} by: {info['createdBy']} comment: {info['comment']}: {e}"
    return output


def delete_silence(filter, alertmanagers):
    output = ""
    all_silences = dict()
    all_silences_list = Parallel(n_jobs=10, verbose=0, backend="threading")(
        map(delayed(get_silences), alertmanagers)
    )
    for silence_instance in all_silences_list:
        all_silences.update(silence_instance)
    list_to_delete = []
    for instance, silences in all_silences.items():
        for silence in silences:
            if datetime.now(timezone.utc) < datetime.strptime(
                silence["endsAt"], "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=timezone.utc):
                filters = ""
                for matcher in silence["matchers"]:
                    filters += f"{matcher_to_str(matcher)},"
                filters.strip(",")
                any_matches = False
                for f in filter.split(","):
                    if f in filters or f in silence["comment"]:
                        any_matches = True
                if any_matches:
                    list_to_delete.append(
                        {
                            "instance": instance,
                            "id": silence["id"],
                            "filters": filters,
                            "createdBy": silence["createdBy"],
                            "comment": silence["comment"],
                        }
                    )
    all_deleted = Parallel(n_jobs=20, verbose=0, backend="threading")(
        map(delayed(delete_cmd), list_to_delete)
    )
    for silence_deleted in all_deleted:
        output += silence_deleted + "\n"
    if len(output.strip("\n")) == 0:
        return "No silences matched."
    return output


def silence_add(command, alertmanagers, user):
    try:
        silence = dict()
        try:
            match = re.match(r"(.*?) (\d+[hmd]?) (.*)", command)
            filters = match.group(1)
            silence["endsAt"] = human_to_ts(match.group(2))
            silence["comment"] = match.group(3)
        except:
            return r"Please include a comment. i.e. `silence MyAlert 1000000d this is my comment` (it must match `(.*?) (\d+[hmd]?) (.*)`)"
        silence["createdBy"] = user
        if "=" in filters or "!=" in filters:
            silence["matchers"] = str_to_matchers(filters)
        else:
            if ".*" in filters:
                silence["matchers"] = [
                    {
                        "name": "alertname",
                        "isEqual": True,
                        "isRegex": True,
                        "value": filters.strip(" "),
                    }
                ]
            else:
                silence["matchers"] = [
                    {
                        "name": "alertname",
                        "isEqual": True,
                        "isRegex": False,
                        "value": filters.strip(" "),
                    }
                ]
        filter_str = ""
        for matcher in silence["matchers"]:
            filter_str += f"{matcher_to_str(matcher)},"
        filter_str.strip(",")
        silence["startsAt"] = (
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )
        for alertmanager in alertmanagers:
            result = requests.post(
                f"https://{alertmanager}/api/v2/silences", json=silence
            )
        return f"Created silence for {filter_str} - expires in {ts_to_human(silence["endsAt"])}"
    except Exception as e:
        return f"Error creating silence {e}"


def silence(command, alertmanagers, user):
    try:
        command = re.match(r"silence (.*)", command).group(1)
        if command.startswith("list"):
            result = silence_summary(alertmanagers)
            logger.info(f"List silence: {result}")
            return result
        elif command.startswith("delete"):
            result = delete_silence(command.lstrip("delete "), alertmanagers)
            logger.info(f"Delete silence: {result}")
            return result
        elif command.startswith("help"):
            return (
                "Command to manage AlertManager silences.\n"
                "format:\n"
                '  silence <alertname|my-tag=".*",my-other-tag="test"|list|delete|help> [duration(m|h|d)] [comment]\n'
                'Filters should be in the prometheus/alertmanager format of key="value" / key=~"value.*"\n'
                "examples:\n"
                "  silence PrometheusDuplicateTimestamps 1000000 this is a comment on the silence\n"
                '  silence my_env=~".*-dev" 1000000 dev cluster maintenance\n'
                "  silence delete dev cluster maintenance\n"
                "  silence list\n"
                "  silence help"
            )
        else:
            result = silence_add(command, alertmanagers, user)
            logger.info(f"Add silence: {result}")
            return result
    except Exception as e:
        import traceback

        print(traceback.format_exc())
        return "There was an error. Sorry."


def condense(string_list):
    common_prefix = ""
    common_suffix = ""
    s = string_list[0]
    for i, char in enumerate(s):
        matches = True
        for s2 in string_list:
            if s2[i] != char:
                matches = False
                break
        if matches:
            common_prefix += char
        else:
            break
    for i, char in enumerate(s[::-1]):
        matches = True
        for s2 in string_list:
            if s2[::-1][i] != char:
                matches = False
                break
        if matches:
            common_suffix += char
        else:
            break
    common_suffix = common_suffix[::-1]
    print(common_prefix)
    print(common_suffix)
    return [s[len(common_prefix) : -len(common_suffix)] for s in string_list]


global amlookup
if __name__ == "__main__":
    import sys
    import os

    amlist = os.getenv("ALERTMANAGER_HOSTS").split(",")
    amshort = condense(amlist)
    amlookup = dict(zip(amlist, amshort))
    print(f'silence {" ".join(list(sys.argv[1:]))}')
    print(
        silence(
            f'silence {" ".join(list(sys.argv[1:]))}',
            amlist,
            os.getenv("USER"),
        )
    )
