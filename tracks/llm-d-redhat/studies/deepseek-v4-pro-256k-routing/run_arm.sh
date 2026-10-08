#!/usr/bin/env bash
# One measured run of the 256K routing comparison for one scheduler arm.
#   run_arm.sh <arm> <label> [concurrency]
#   arm: random | optimized-baseline | optimized-baseline-tuned
#        (paths/01-optimized-baseline/deepseek-v4-pro-h200/router/rendered-<arm>.yaml)
# Every arm gets the same sequence: apply the arm's scheduler config, restart the
# router (its prefix index lives in memory), wait for all replicas, reset every
# replica's prefix cache, then replay the same 32-session 256K dataset through the
# router. Results land in raw/<label>/ next to this script.
set -euo pipefail
arm=${1:?arm}; label=${2:?label}; concurrency=${3:-8}
ctx=${KUBE_CONTEXT:-gpu-cluster}; ns=llm-d
here=$(cd "$(dirname "$0")" && pwd)
router="$here/../../paths/01-optimized-baseline/deepseek-v4-pro-h200/router"
out="$here/raw"
k() { kubectl --context "$ctx" -n "$ns" "$@"; }

replicas=$(k get statefulset deepseek-v4-pro -o jsonpath='{.spec.replicas}')
k wait --for=condition=Ready pod -l llm-d.ai/model=deepseek-v4-pro --timeout=10m
ready=$(k get pods -l llm-d.ai/model=deepseek-v4-pro -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' | grep -c true)
[ "$ready" = "$replicas" ] || { echo "only $ready/$replicas replicas ready" >&2; exit 1; }

k apply -f "$router/rendered-$arm.yaml" >/dev/null
k rollout restart deploy/llmd-epp >/dev/null
k rollout status deploy/llmd-epp --timeout=5m
deployment="deployment-$arm.json"
k cp "$here/$deployment" benchmark-client:/bench/deployment.json

metrics=()
for i in $(seq 0 $((replicas - 1))); do
  metrics+=(--metrics-url "http://deepseek-v4-pro-$i.deepseek-v4-pro.$ns.svc.cluster.local:8000/metrics")
done
metrics+=(--metrics-url "http://llmd-epp.$ns.svc.cluster.local:9090/metrics")

k exec benchmark-client -- mkdir -p "/bench/results/$label"
# Wait until the router has discovered every replica, then reset all prefix caches.
k exec -i benchmark-client -- python - "$replicas" "$ns" "$label" "$arm" <<'PY'
import json, sys, time, httpx
n, ns, label, arm = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
deadline = time.time() + 120
while True:
    text = httpx.get(f'http://llmd-epp.{ns}.svc.cluster.local:9090/metrics', timeout=10).text
    ready = [float(l.split()[-1]) for l in text.splitlines() if l.startswith('llm_d_epp_ready_endpoints')]
    pods = int(max(ready, default=0))
    if pods >= n:
        break
    assert time.time() < deadline, f'router sees {pods}/{n} ready endpoints'
    time.sleep(5)
records = []
for i in range(n):
    url = f'http://deepseek-v4-pro-{i}.deepseek-v4-pro.{ns}.svc.cluster.local:8000/reset_prefix_cache'
    r = httpx.post(url, timeout=120)
    records.append({'replica': i, 'status': r.status_code, 'body': r.text[:200], 'time': time.time()})
    assert r.status_code == 200, records[-1]
evidence = {'label': label, 'arm': arm, 'router_ready_endpoints': pods, 'cache_resets': records}
json.dump(evidence, open(f'/bench/results/{label}/pre-run.json', 'w'), indent=2)
print(json.dumps(evidence))
PY

k exec benchmark-client -- python -m benchmarks.run \
  --base-url "http://llmd-epp.$ns.svc.cluster.local:80/v1" \
  --model deepseek-ai/DeepSeek-V4-Pro-0813 --technology llmd-k8s \
  --deployment /bench/deployment.json \
  --dataset datasets/generated/deepseek-v4-pro-chatbot-256k-32.jsonl \
  --max-model-len 262144 --min-input-tokens 250001 --output-tokens 256 \
  --concurrency "$concurrency" --warmup 1 --timeout 3600 --temperature 0 \
  --cache-state mixed "${metrics[@]}" --results "/bench/results/$label"

mkdir -p "$out"
k exec benchmark-client -- tar czf - -C /bench/results "$label" | tar xzf - -C "$out"
k logs deploy/llmd-epp -c epp --since=2h > "$out/$label/epp.log"
echo "saved $out/$label"
