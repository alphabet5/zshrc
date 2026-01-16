# random kubernetes commands


## finding things not owned by flux

```bash
kubectl get deployment,statefulset -A -o json | jq -r '.items[] | select(.metadata.labels["helm.toolkit.fluxcd.io/name"] == null and .metadata.labels["kustomize.toolkit.fluxcd.io/name"] == null) | [.metadata.namespace, .metadata.name] | @tsv'
```

