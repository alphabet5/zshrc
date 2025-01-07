function run-command(){
    n=$#
    for ((i=1; i<$n; i++)); do
        if [ -n "$ZSH_VERSION" ]; then
            echo "${(P)i}"
            ssh -oStrictHostKeyChecking=accept-new -A "${(P)i}" "${(P)n}";
        elif [ -n "$BASH_VERSION" ]; then
            echo "${!i}"
            ssh -oStrictHostKeyChecking=accept-new -A "${!i}" "${!n}";
        else
            echo "Unknown shell"
        fi;
    done
}
