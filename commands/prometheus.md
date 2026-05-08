# Some helpful prometheus/thanos queries

metrics to csv

node os's

```
curl -s -X POST "https://$PROM_HOST$/api/v1/query" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-raw "query=node_os_info * on(instance, job) group_left(nodename) node_uname_info&dedup=true&partial_response=true&time=$(date +%s.%N)&engine=prometheus&analyze=false&tenant=" \
  -H "Accept: application/json" | jq -r '.data.result[] | [(.metric.nodename | capture("^(?<short>[^.]+)")).short, (.metric.instance | capture("^(?<name>[^:]+)")).name, .metric.pretty_name] | @tsv' | pbcopy
```

node kernels

```
curl -s -X POST "https://$PROM_HOST/api/v1/query" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-raw "query=node_uname_info&dedup=true&partial_response=true&time=$(date +%s.%N)&engine=prometheus&analyze=false&tenant=" \
  -H "Accept: application/json" | jq -r '.data.result[] | [(.metric.nodename | capture("^(?<short>[^.]+)")).short, (.metric.instance | capture("^(?<name>[^:]+)")).name, .metric.release] | @tsv' | pbcopy
```

daemonsets stuck

```
curl -s -X POST "https://$PROM_HOST/api/v1/query" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-raw "query=sum%28ALERTS%7Balertname%3D%7E%22KubernetesDaemonsetRolloutStuck%22%7D%29+by+%28k8s_cluster%2C+daemonset%2C+namespace%29&dedup=true&partial_response=true&time=$(date +%s.%N)&engine=prometheus&analyze=false&tenant=" \
  -H "Accept: application/json" | jq -r '.data.result[] | "kubectl rollout restart daemonset " + .metric.daemonset + " -n " + .metric.namespace + " --context=" + .metric.k8s_cluster'
```