#!/bin/bash
# Kill one pod of a role and timestamp recovery: ./inject.sh decode|prefill|frontend
set -euo pipefail
role=${1:?role}; ns=${NAMESPACE:-nemotron-3-nano}; k="kubectl --context ${KUBE_CONTEXT:?set KUBE_CONTEXT} -n $ns"
pod=$($k get pods -l nvidia.com/dynamo-component-type=$role -o jsonpath='{.items[0].metadata.name}')
echo "$(date -u +%FT%TZ) delete $pod"
$k delete pod "$pod" --wait=false
until [ "$($k get pods -l nvidia.com/dynamo-component-type=$role -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep -c True)" -ge "$($k get pods -l nvidia.com/dynamo-component-type=$role --no-headers | wc -l)" ]; do sleep 5; done
echo "$(date -u +%FT%TZ) all $role pods Ready"
