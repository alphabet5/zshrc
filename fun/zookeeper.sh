# this is just some common zk commands, that probably shouldn't work if things are locked down.
zk() {
  case "$1" in
    stat)
      echo "stat" | nc -w 3 $2 2181
    ;;
    ruok)
      echo "ruok" | nc -w 3 $2 2181
    ;;
    leader)
      echo "srvr" | nc -w 3 $2 2181 | grep Mode
    ;;
  esac
}
