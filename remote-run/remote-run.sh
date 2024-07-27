# # this is just an example
# dothething () {
# bash -c 'set -e; for host in ${HOSTGROUP}; do echo "doing the thing on ${host}"; for retry in {1..4}}; do ssh -oStrictHostKeyChecking=accept-new -A $host "sudo do the thing &" && break || sleep 5;done;done;'
# }
