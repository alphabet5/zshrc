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
