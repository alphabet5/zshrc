function isup() {
    emulate -L zsh  # Safe environment in zsh
    setopt local_options NO_NOMATCH  # Prevent globbing errors
    set +m

    local max_concurrent=10
    local running=0
    local host
    local pids=()

    for host in "$@"; do
        {
            if ping -c 4 -W 1 "$host" > /dev/null 2>&1; then
                echo -e "$host\tup"
            else
                echo -e "$host\tdown"
            fi
        } &

        pids+=($!)
        (( running++ ))

        if (( running >= max_concurrent )); then
            wait $pids[1]
            pids=(${pids[@]:1})  # Remove first finished job
            (( running-- ))
        fi
    done

    # Wait for any remaining jobs
    for pid in $pids; do
        wait $pid
    done
    set -m
}