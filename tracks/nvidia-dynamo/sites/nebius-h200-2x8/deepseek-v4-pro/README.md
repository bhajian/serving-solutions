# DeepSeek V4 Pro on Nebius H200 with Dynamo and SGLang

This site deployment serves `deepseek-ai/DeepSeek-V4-Pro-0813`, revision
`72e1d3230f6c080a530b0a1d46f8eb4602340597`, on two TP8 H200 workers.
The active manifests now run **two aggregated replicas**, following the matched
[256K-context comparison](../../../studies/deepseek-v4-pro-256k-comparison/REPORT.md). The disaggregated alternative uses
one TP8 prefill worker and one TP8 decode worker with NIXL/InfiniBand KV transfer.
Both configurations use a 262,144-token context window and four running requests
per worker. The public LoadBalancer remains on port 8000.

The shared cluster was subsequently switched to the [Nemotron 3 Nano profile](../nemotron-3-nano/)
for its 128K comparison. This folder remains the saved DeepSeek configuration;
its weights and PVCs are retained. Restore this folder's `30-frontend.yaml` as
well as the selected worker manifest when switching back from Nemotron.

The original reference manifests target B300/Nemotron and cannot be applied
unchanged here: model paths, quantization kernels, memory limits, node placement,
and storage must match H200. This folder uses the Marlin MoE backend, a 1300Gi
worker memory limit, and one 1500Gi Nebius RWO PVC per node. Checkpoint downloads
run as Jobs; workers wait for the pinned revision marker before loading.

Workers enable `--weight-loader-prefetch-checkpoints`. Without it, this runtime
stalled after reading all shards: concurrent weight-copy threads blocked in
`cuMemcpyHtoDAsync` / `pthread_rwlock_wrlock`. The checkpoint fits in node RAM,
so prefetch can warm the page cache for GPU copies. On this cluster the first
download took about 32 minutes per node and cold prefetch took about 23 minutes;
kernel warmup follows. See
[SGLang issue #29268](https://github.com/sgl-project/sglang/issues/29268).

## Switch between topologies

The model revision, completed download Jobs, PVCs and LoadBalancer are shared.
Switch to prefill/decode disaggregation using:

```bash
kubectl --context $KUBE_CONTEXT apply -f tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/lab/as-measured/workers-tp8-disaggregated/40-workers-disaggregated.yaml
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro rollout status deployment/worker-0 --timeout=2h
kubectl --context $KUBE_CONTEXT -n deepseek-v4-pro rollout status deployment/worker-1 --timeout=2h
```

For that topology, benchmark with `deployment-disaggregated.json`. To return to
two aggregated replicas, apply `40-workers.yaml` and wait for both rollouts; use
`deployment.json` for benchmarks. These changes restart workers and temporarily
interrupt inference. They do not rerun downloads or create new model volumes.
Use the explicit worker file or the provided kustomization; do not apply both
alternative worker manifests together. The kustomization deploys aggregated mode.

## Deploy from the repository root

Always specify the intended context. The local default context may point at a
separate CPU cluster. Edit the `kubernetes.io/hostname` selectors in the download,
frontend and worker manifests when using another cluster. Keep each worker and
its download Job on the same node; frontend shares `model-0` with worker 0.

```bash
export KUBE_CONTEXT=<your-kube-context>
kubectl --context "$KUBE_CONTEXT" get nodes -o wide
kubectl --context "$KUBE_CONTEXT" apply -f tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/lab/as-measured/namespace/00-namespace.yaml

# Set HF_TOKEN in your shell without putting it in a tracked file.
# Feed the Secret through stdin so its value is not a kubectl process argument.
python3 - <<'PY' | kubectl --context "$KUBE_CONTEXT" apply --server-side -f -
import json, os
print(json.dumps({"apiVersion":"v1", "kind":"Secret",
    "metadata":{"name":"hf-token", "namespace":"deepseek-v4-pro"},
    "type":"Opaque", "stringData":{"HF_TOKEN":os.environ["HF_TOKEN"]}}))
PY

kubectl --context "$KUBE_CONTEXT" apply --dry-run=server -k tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro
kubectl --context "$KUBE_CONTEXT" apply -k tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro
kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro logs -f job/download-0
# In another terminal, inspect download-1 too.
kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro wait --for=condition=complete job/download-0 job/download-1 --timeout=4h
kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro rollout status deployment/worker-0 --timeout=2h
kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro rollout status deployment/worker-1 --timeout=2h
kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro rollout status deployment/frontend --timeout=10m
```

Downloading and loading this checkpoint can take hours. A frontend `/health`
response alone does not prove inference readiness. Check both worker rollouts,
then test through the external address:

```bash
export ENDPOINT="http://$(kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro get service frontend -o jsonpath='{.status.loadBalancer.ingress[0].ip}'):8000"
python3 tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/smoke_test.py "$ENDPOINT"
curl --fail-with-body --max-time 300 "$ENDPOINT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-ai/DeepSeek-V4-Pro-0813","messages":[{"role":"user","content":"Explain how Kubernetes routes a request from a LoadBalancer to a GPU model server in three sentences."}],"max_tokens":256,"temperature":0,"chat_template_kwargs":{"thinking":false}}'
```

The LoadBalancer is public HTTP with no API authentication. Restrict
`spec.loadBalancerSourceRanges` or add an authenticated TLS gateway if needed.
The Hugging Face token is only used by the download Jobs, not exposed by the API.

## Operations

Inspect `kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro get pods,pvc,svc`
and the worker logs when startup fails. Both workers reserve all eight GPUs of
their node; unrelated GPU workloads prevent scheduling. Startup probes allow two
hours after the worker container starts; no liveness probe kills long requests.
The disaggregated alternative uses NIXL with the eight `mlx5_0`–`mlx5_7` HCAs. The worker requires accessible
InfiniBand devices and `IPC_LOCK`/`SYS_RESOURCE` capabilities to unlock registered
GPU memory. `UCX_TLS` excludes TCP, so this configuration requires working RDMA.
Host networking exposes the prefill bootstrap port 8998 between nodes.
Do not enable offline mode for download Jobs. Worker/frontends use offline mode
and mount the checkpoint read-only.

The two model PVCs are bound to persistent Nebius network SSD disks. A replacement
pod reuses its checkpoint without downloading it again. These are separate RWO
volumes, not a shared RWX filesystem. Shared filesystem work is deferred. Compiled
kernel caches now persist under `.runtime` on each existing PVC and are mounted
writable separately from the read-only checkpoint. A restart still reloads GPU
weights and initializes kernels; a cold node must read the checkpoint from disk
again. Each cache belongs to this pinned runtime and GPU architecture; use a new
cache directory when changing either.

To change checkpoint revision, use new PVCs and matching download/worker
revision checks; do not combine files from different revisions. Stop workers
before changing their shared model files. PVCs survive deleting a Deployment,
but **deleting this namespace or running `kubectl delete -k` deletes the PVCs and
underlying model disks**. To stop compute without deleting cached weights:

```bash
kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro scale deployment/worker-0 deployment/worker-1 --replicas=0
```

Sources: [SGLang DeepSeek V4 cookbook](https://github.com/sgl-project/sglang/blob/main/docs/cookbook/autoregressive/DeepSeek/DeepSeek-V4.mdx),
[Dynamo DeepSeek V4 recipes](https://github.com/ai-dynamo/dynamo/tree/main/recipes/deepseek-v4),
[Dynamo 1.4.0 SGLang disaggregated launch](https://github.com/ai-dynamo/dynamo/blob/v1.4.0/examples/backends/sglang/launch/disagg.sh).

## Run the repository benchmark

For the full concurrency sweep and notebook workflow, see
[Performance testing](PERFORMANCE.md). The small run below is a functional check.

Install the repository requirements in `.venv` first. Download only the small
tokenizer/encoder files onto the client; weights remain on the cluster PVCs:

```bash
.venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('deepseek-ai/DeepSeek-V4-Pro-0813',
    revision='72e1d3230f6c080a530b0a1d46f8eb4602340597',
    local_dir='build/deepseek-v4-pro-tokenizer',
    allow_patterns=['*.json', '*.jinja', '*.py', '*.model', '*.txt'])
PY
.venv/bin/python -m benchmarks.generate_dataset --workload chatbot --sessions 4 \
  --input-tokens 8000 --output-tokens 128 --max-model-len 262144 \
  --tokenizer build/deepseek-v4-pro-tokenizer \
  --deepseek-v4-encoder build/deepseek-v4-pro-tokenizer/encoding/encoding_dsv4.py \
  --trust-remote-code --template-kwargs '{"thinking":false}' \
  --out datasets/generated/deepseek-v4-pro-h200-8k.jsonl
.venv/bin/python -m benchmarks.run --base-url "$ENDPOINT/v1" \
  --model deepseek-ai/DeepSeek-V4-Pro-0813 --technology dynamo-agg-k8s \
  --deployment tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/lab/as-measured/records/deployment.json \
  --dataset datasets/generated/deepseek-v4-pro-h200-8k.jsonl \
  --max-model-len 262144 --min-input-tokens 8000 --output-tokens 128 --concurrency 4
```

The dataset generator intentionally refuses to overwrite an existing dataset;
reuse it on subsequent benchmark runs. Four sessions contain twelve requests.
Measurements from an external client include WAN and LoadBalancer latency.
