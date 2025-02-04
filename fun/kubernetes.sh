seal(){
echo -n $1 | kubeseal --scope=$KUBESEAL_SCOPE --raw --from-file=/dev/stdin --cert=$KUBESEAL_CERT
}
sealnc() {
  echo -n $1 | kubeseal --scope=$KUBESEAL_SCOPE --raw --from-file=/dev/stdin --controller-name=sealed-secrets-controller --controller-namespace=sealed-secrets
}
kgp() {
  if [ $2 ]; then
    a=$(kubectl get pods -o json -A | jq -r '.items[] | select((.metadata.name | test("'$1'")) or (.metadata.labels? | select(type == "object") | to_entries | any(.value | test("'$1'")))) | select((.metadata.name | test("'$2'")) or (.metadata.labels[] | test("'$2'"))) | "\(.metadata.namespace) \(.metadata.name)"')
  else
    a=$(kubectl get pods -o json -A | jq -r '.items[] | select((.metadata.name | test("'$1'")) or (.metadata.labels? | select(type == "object") | to_entries | any(.value | test("'$1'")))) | "\(.metadata.namespace) \(.metadata.name)"')
  fi
  echo $a | awk '{ print length($0) " " $0; }' | sort -n | cut -d " " -f 2- | grep -m 1 .
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
      echo "echo \$(ssh $node \"sudo CRI_CONFIG_FILE=/var/lib/rancher/rke2/agent/etc/crictl.yaml /var/lib/rancher/rke2/bin/crictl inspect -o yaml $cid\") | yq '.info.pid'"
      all=$(ssh $node "sudo CRI_CONFIG_FILE=/var/lib/rancher/rke2/agent/etc/crictl.yaml /var/lib/rancher/rke2/bin/crictl inspect -o yaml $cid")
      # echo $all
      # yq avoids issues with newlines and json quoting weirdness / invalid json output from crictl
      # https://github.com/kubernetes-sigs/cri-tools/pull/1493 (plus some other issues)
      pid=$(echo $all | yq '.info.pid')
      echo "ssh -t ${node} 'sudo nsenter -t ${pid} -n -- bash -l'"
      ssh -t $node 'sudo nsenter -t '$pid' -n -- bash -l'
      ;;
    l)
      echo $a
      echo "kubectl logs -f -n ${pod[1]} ${pod[2]}"
      kubectl logs -f -n ${pod[1]} ${pod[2]}
      ;;
    c) 
      kubectl config use-context $2
      ;;
    certs)
      ssh $2 "timeout 1 openssl s_client -connect 127.0.0.1:10257 -showcerts 2>&1 | grep -A 19 -m 1 'BEGIN CERTIFICATE' | sudo tee /var/lib/rancher/rke2/server/tls/kube-controller-manager/kube-controller-manager.crt & timeout 1 openssl s_client -connect 127.0.0.1:10259 -showcerts 2>&1 | grep -A 19 -m 1 'BEGIN CERTIFICATE' | sudo tee /var/lib/rancher/rke2/server/tls/kube-scheduler/kube-scheduler.crt &"
      ;;
    ceph)
      case "$2" in
        archive)
          kubectl rook-ceph ceph crash ls | grep -v '^ID' | awk '{print $1}' | xargs -L 1 kubectl rook-ceph ceph crash archive
          ;;
        *)
          kubectl rook-ceph "$@"
          ;;
      esac
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
