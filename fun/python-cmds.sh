function actions() {
  python3 $MYDIR/python/actions.py "$@"
}

function filter() {
  python3.12 $MYDIR/python/filter.py "$@"
}

function jira() {
  python3.12 $MYDIR/python/j.py "$@"
}

function nsr() {
  python3.12 $MYDIR/python/nsr.py "$@"
}

function silence() {
  python3.12 $MYDIR/python/silence.py "$@"
}

function poweroff-host() {
    python3.12 $MYDIR/python/reboot-bmc.py poweroff "$@"
}

function reboot-host() {
  python3.12 $MYDIR/python/reboot-bmc.py reboot "$@"
}

function boot-host() {
  python3.12 $MYDIR/python/reboot-bmc.py boot "$@"
}

function run-commands() {
  python3.12 $MYDIR/python/run-commands.py "$@"
}

function ysort() {
  python3.12 $MYDIR/python/ysort.py "$@"
}

function summary() {
    python3.12 $MYDIR/python/summary-networks.py "$@"
}

function inverse() {
    python3.12 $MYDIR/python/summary-networks.py "$@"
}
