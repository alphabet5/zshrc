KUBESEAL_CERT="Documents/GitHub/kubernetes-ops/sealedsecrets.crt"
KUBESEAL_SCOPE="cluster-wide"
seal(){
echo -n $1 | kubeseal --scope=$KUBESEAL_SCOPE --raw --from-file=/dev/stdin --cert=$KUBESEAL_CERT
}
kgp() {
  if [ $2 ]; then
    a=$(kubectl get pods -o json -A | jq -r '.items[] | select(.metadata.namespace | test(".*'$1'.*")) | select((.metadata.name | test(".*'$2'.*")) or (.metadata.labels[] | test(".*'$2'.*"))) | "\(.metadata.namespace) \(.metadata.name)"')
  else
    a=$(kubectl get pods -o json -A | jq -r '.items[] | select((.metadata.name | test(".*'$1'.*")) or (.metadata.labels[] | test(".*'$1'.*"))) | "\(.metadata.namespace) \(.metadata.name)"')
  fi
  echo $a | awk '{ print length($0) " " $0; }' $file | sort -n | cut -d " " -f 2- | grep -m 1 .
}
kgpa() {
  if [ $2 ]; then
    echo $(kubectl get pods -o json -A | jq -r '.items[] | select(.metadata.namespace | test(".*'$1'.*")) | select((.metadata.name | test(".*'$2'.*")) or (.metadata.labels[] | test(".*'$2'.*"))) | ""')
  else
    echo $(kubectl get pods -o json -A | jq -r '.items[] | select((.metadata.name | test(".*'$1'.*")) or (.metadata.labels[] | test(".*'$1'.*"))) | "\(.metadata.namespace) \(.metadata.name)"')
  fi
}
logspods() {
  if [ $2 ]; then
    a=$(kubectl get pods -o json -A | jq -r '.items[] | select(.metadata.namespace | test(".*'$1'.*")) | select((.metadata.name | test(".*'$2'.*")) or (.metadata.labels[] | test(".*'$2'.*"))) | .metadata.labels | add')
  else
    a=$(kubectl get pods -o json -A | jq -r '.items[] | select((.metadata.name | test(".*'$1'.*")) or (.metadata.labels[] | test(".*'$1'.*"))) | .metadata.labels | add')
  fi
  echo $a | awk '{ print length($0) " " $0; }' $file | sort -n | cut -d " " -f 2- | grep -m 1 .
}
k() {
  if [ $3 ]; then
    pod=($(kgp $2 $3))
  else
    pod=($(kgp $2))
  fi
  case "$1" in
    ex)
      echo "kubectl exec --stdin --tty -n "${pod[1]}" "${pod[2]}" -- bash"
      kubectl exec --stdin --tty -n ${pod[1]} ${pod[2]} -- bash
      ;;
    exsh)
      echo "kubectl exec --stdin --tty -n "${pod[1]}" "${pod[2]}" -- sh"
      kubectl exec --stdin --tty -n ${pod[1]} ${pod[2]} -- sh
      ;;
    sniff)
      if [ $5 ]; then
        echo "kubectl sniff -p --socket /run/k3s/containerd/containerd.sock -n "${pod[1]}" "${pod[2]}" "$4" "$5""
        kubectl sniff -p --socket /run/k3s/containerd/containerd.sock -n ${pod[1]} ${pod[2]} $4 $5
      else
        echo "kubectl sniff -p --socket /run/k3s/containerd/containerd.sock -n "${pod[1]}" "${pod[2]}""
        kubectl sniff -p --socket /run/k3s/containerd/containerd.sock -n ${pod[1]} ${pod[2]}
      fi
      ;;
    nsenter)
      echo "kubectl get pod -n "${pod[1]}" "${pod[2]}" -o yaml | yq '.status.containerStatuses[0].containerID' | sed -r 's/containerd:\/\/(.*)/\1/g'"
      cid=($(kubectl get pod -n "${pod[1]}" "${pod[2]}" -o yaml | yq '.status.containerStatuses[0].containerID' | sed -r 's/containerd:\/\/(.*)/\1/g'))
      echo "kubectl get pod -n "${pod[1]}" "${pod[2]}" -o yaml | yq '.spec.nodeName'"
      node=$(kubectl get pod -n "${pod[1]}" "${pod[2]}" -o yaml | yq '.spec.nodeName')
      echo "(ssh $node 'sudo CRI_CONFIG_FILE=/var/lib/rancher/rke2/agent/etc/crictl.yaml /var/lib/rancher/rke2/bin/crictl inspect '$cid) | jq '.info.pid'"
      pid=($(echo $(ssh $node 'sudo CRI_CONFIG_FILE=/var/lib/rancher/rke2/agent/etc/crictl.yaml /var/lib/rancher/rke2/bin/crictl inspect '$cid) | jq '.info.pid'))
      echo "ssh ${node} 'sudo nsenter -t ${pid} -n; exec bash'"
      ssh $node 'sudo nsenter -t '$pid' -n; exec bash'
      ;;
    l)
      echo $a
      echo "kubectl logs -f -n ${pod[1]} ${pod[2]}"
      kubectl logs -f -n ${pod[1]} ${pod[2]}
      ;;
    p)
      echo pod
      ;;
  esac
}
ex()
{
if [ -z "$2" ]; then
a=($(kubectl get pods -A -o json | jq -r '[.items[] | select((.metadata.name | test(".*'$1'.*")) or (.metadata.labels[] | test(".*'$1'.*")) ) | [.metadata.namespace, .metadata.name]][0] | .[]'))
else
a=($(kubectl get pods -n $1 -o json | jq -r '[.items[] | select((.metadata.name | test(".*'$2'.*")) or (.metadata.labels[] | test(".*'$2'.*")) ) | [.metadata.namespace, .metadata.name]][0] | .[]'))
fi
echo "kubectl exec --stdin --tty -n "${pod[1]}" "${pod[2]}" -- bash"
kubectl exec --stdin --tty -n ${pod[1]} ${pod[2]} -- bash
}
exsh()
{
if [ -z "$2" ]; then
a=($(kubectl get pods -A -o json | jq -r '[.items[] | select((.metadata.name | test(".*'$1'.*")) or (.metadata.labels[] | test(".*'$1'.*")) ) | [.metadata.namespace, .metadata.name]][0] | .[]'))
else
a=($(kubectl get pods -n $1 -o json | jq -r '[.items[] | select((.metadata.name | test(".*'$2'.*")) or (.metadata.labels[] | test(".*'$2'.*")) ) | [.metadata.namespace, .metadata.name]][0] | .[]'))
fi
echo "kubectl exec --stdin --tty -n "${pod[1]}" "${pod[2]}" -- sh"
kubectl exec --stdin --tty -n ${pod[1]} ${pod[2]} -- sh
}
