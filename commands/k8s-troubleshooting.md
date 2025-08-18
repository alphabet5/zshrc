

## etcd

```
export ETCDCTL_ENDPOINTS='https://127.0.0.1:2379'
export ETCDCTL_CACERT='/var/lib/rancher/rke2/server/tls/etcd/server-ca.crt'
export ETCDCTL_CERT='/var/lib/rancher/rke2/server/tls/etcd/server-client.crt'
export ETCDCTL_API=3

```

```
kubectl -n kube-system exec $(kubectl -n kube-system get pod -l component=etcd --no-headers -o custom-columns=NAME:.metadata.name | head -1) -- etcdctl --cert /var/lib/rancher/rke2/server/tls/etcd/server-client.crt --key /var/lib/rancher/rke2/server/tls/etcd/server-client.key --cacert /var/lib/rancher/rke2/server/tls/etcd/server-ca.crt defrag --cluster
```



