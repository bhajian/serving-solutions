# Aggregated serving · Dynamo + vLLM · Kubernetes

[Home](../../../../../../README.md) › [Tracks](../../../../../README.md) › [NVIDIA Dynamo](../../../../README.md) › [Sites](../../../README.md) › [hgx-b300-2x8](../../README.md) › [01-aggregated](../README.md) › [vllm](README.md) › Kubernetes

Plain Kubernetes manifests: Deployments, Services and one ConfigMap. No operator or CRDs. Every process, flag and port is visible in the YAML, so you can see exactly what Dynamo needs. Numbered file prefixes give the apply order.

## What you deploy

| File | Kubernetes objects | Runs on |
|---|---|---|
| [00-namespace.yaml](00-namespace.yaml) | Namespace `dynamo-agg-vllm` | n/a |
| [01-site-config.yaml](01-site-config.yaml) | ConfigMap `site-config`: Ethernet interface. **Check this.** | n/a |
| [10-etcd.yaml](10-etcd.yaml) | Deployment + Service `etcd` | any node |
| [20-frontend.yaml](20-frontend.yaml) | Deployment + Service `frontend` (API :8000, host network) | `llm-serving/node=node-a` |
| [30-worker.yaml](30-worker.yaml) | Deployment `worker`, **2 replicas**, 8 GPUs each, one per labeled node | `node-a`, `node-b` |
| [kustomization.yaml](kustomization.yaml) | Lists the files above for `kubectl apply -k` | n/a |
| [deployment.json](deployment.json) | Run record for the benchmark. Not a Kubernetes object. | n/a |

![Reference topology: Node A runs etcd, the frontend and a worker; Node B runs a worker; Ethernet carries control traffic and InfiniBand carries KV cache](../../../../../../assets/diagrams/png/b300-reference.png)

**Design choices worth knowing**

- **Host networking for frontend and workers.** Dynamo's request plane use the nodes' private IPs directly, as in the Docker deployment. Each pod learns its IP from the Downward API (`status.hostIP`).
- **Node placement by label** (`llm-serving/node`), so no hostnames are hard-coded.
- **etcd behind a Service.** Host-network pods reach it by DNS (`etcd.dynamo-agg-vllm.svc.cluster.local`) thanks to `dnsPolicy: ClusterFirstWithHostNet`.
- **Weights from `hostPath`.** The workers are pinned to nodes that already hold the checkpoint. A shared, read-only model volume is the production alternative ([production operations](../../../../../../blueprint/10-production-operations.md)).
- **Long startup, no liveness probe.** The startup probe allows up to 2 hours for loading and compilation. There is deliberately no liveness probe, so a long prefill never gets a worker killed.

## Before you start

- [ ] [00 · Prerequisites](../../../../../../platform/prerequisites/) done, including the model at `/data/nemotron-ultra/model` on each GPU node you use.
- [ ] GPU nodes labeled ([prerequisites §7](../../../../../../platform/prerequisites/#kubernetes-path)):

  ```bash
  kubectl get nodes -L llm-serving/node      # expect node-a and node-b
  ```

- [ ] `01-site-config.yaml` checked: `IP_IFACE` matches your nodes. If your model is not at `/data/nemotron-ultra/model`, edit the `hostPath` in `20-frontend.yaml` and `30-worker.yaml`.
- [ ] No other track is running on these GPUs. Delete its namespace first; see "Clean up" in that track's README.
- [ ] Commands run **from the repository root** on a machine with `kubectl` access.

## Step 1 · Namespace and site settings

```bash
kubectl apply -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm/00-namespace.yaml
kubectl apply -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm/01-site-config.yaml
kubectl -n dynamo-agg-vllm get configmap site-config -o yaml
```

## Step 2 · etcd

```bash
kubectl apply -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm/10-etcd.yaml
kubectl -n dynamo-agg-vllm rollout status deployment/etcd --timeout=5m
```

## Step 3 · Frontend

```bash
kubectl apply -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm/20-frontend.yaml
kubectl -n dynamo-agg-vllm rollout status deployment/frontend --timeout=10m
kubectl -n dynamo-agg-vllm logs deployment/frontend --tail=20
```

The frontend becomes Ready before any model is registered. It only lists the model once workers join.

## Step 4 · GPU workers

Optionally, check the manifests against the API server first:

```bash
kubectl apply --dry-run=server -k tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm
```

Then apply:

```bash
kubectl apply -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm/30-worker.yaml
kubectl -n dynamo-agg-vllm get pods -o wide          # confirm each pod landed on the intended node
```

## Step 5 · Wait for initialization

```bash
kubectl -n dynamo-agg-vllm logs -f -l app=worker --max-log-requests=2 --prefix
kubectl -n dynamo-agg-vllm rollout status deployment/worker --timeout=120m
```

Loading the ~352 GB checkpoint and compiling kernels takes a while (tens of minutes on first start; caches make restarts faster). Wait for `VllmWorker ... has been initialized` and `Registered base model` in the **current** startup's logs.

A pod stuck in `Pending` usually means a missing node label or GPUs held by another pod. Run `kubectl -n dynamo-agg-vllm describe pod <pod>` and read the events.

## Step 6 · Verify the API

```bash
kubectl -n dynamo-agg-vllm port-forward service/frontend 8000:8000
# in another terminal:
curl -fsS http://127.0.0.1:8000/v1/models                 # must list nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4
curl --fail-with-body -sS --max-time 300 http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4",
       "messages":[{"role":"user","content":"Explain prefill and decode in three sentences."}],
       "max_tokens":256,"temperature":0,
       "chat_template_kwargs":{"enable_thinking":false,"force_nonempty_content":true}}'
```

Because the frontend uses host networking, clients in the private network can also call `http://<node-a-ip>:8000` directly.

## Step 7 · Watch the router balance the replicas

With two replicas, send the same long prompt twice and a different one once. The KV-aware router should send the repeat to the replica that already caches its prefix. Look at the frontend logs for routing decisions and at each worker's prefix-cache metrics:

```bash
curl -s http://<node-a-ip>:8081/metrics | grep -Ei 'prefix|cache_hit|kv' | head
curl -s http://<node-b-ip>:8081/metrics | grep -Ei 'prefix|cache_hit|kv' | head
```

Metric names vary between versions. What matters is that both workers receive traffic and repeated prefixes produce cache hits.

## Step 8 · See the results

Run a small, repeatable benchmark from any machine that has the benchmark virtualenv ([prerequisites §2](../../../../../../platform/prerequisites/#2-software)) and the model's tokenizer files. Node A works.

```bash
source .venv/bin/activate

# 1) Build a dataset once: 8 chat sessions, ~8K-token prompts (fits the 32K context).
python -m benchmarks.generate_dataset --workload chatbot --sessions 8 \
  --input-tokens 8000 --output-tokens 256 --max-model-len 32768 \
  --tokenizer /data/nemotron-ultra/model --trust-remote-code \
  --template-kwargs '{"enable_thinking":false,"force_nonempty_content":true}' \
  --out datasets/generated/nemotron-chatbot-8k.jsonl

# 2) Measure this deployment.
python -m benchmarks.run \
  --base-url http://127.0.0.1:8000/v1 \
  --model nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4 \
  --technology dynamo-agg-k8s \
  --deployment tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm/deployment.json \
  --dataset datasets/generated/nemotron-chatbot-8k.jsonl \
  --max-model-len 32768 --output-tokens 256 --concurrency 4
```

The URL uses the port-forward from step 6. That is fine for a quick look. For real measurements, run the client on a machine in the private network and use `http://<node-a-ip>:8000/v1`, because port-forward can become the bottleneck.

Each request prints `TTFT=...ms`. The run ends with `Results: tracks/nvidia-dynamo/studies/<run-id>/`, which contains `summary.csv` with TTFT, TPOT, ITL and throughput percentiles. Use **the same dataset file** on every track, then compare them side by side in [benchmarks/README.md](../../../../../../benchmarks/README.md).

## One-shot apply

Once you know the steps, the whole folder can be applied at once. The Kustomization lists the numbered files in order:

```bash
kubectl apply -k tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm
```

## Scaling the aggregated replicas

Aggregated serving scales by adding identical replicas. The Deployment asks for one replica per labeled node:

```bash
kubectl -n dynamo-agg-vllm scale deployment/worker --replicas=1   # single-node lab, or free Node B
kubectl -n dynamo-agg-vllm scale deployment/worker --replicas=2   # both nodes
```

To use more GPU nodes, label them `llm-serving/node=node-c` and so on, add the values to the `nodeAffinity` list in `30-worker.yaml`, and scale up. The router picks new replicas up from etcd automatically.

To change the model, context length or image, edit `30-worker.yaml` and re-apply it. `strategy: Recreate` stops the old pods before starting new ones, because each pod needs all 8 GPUs of its node.

## Clean up

```bash
kubectl delete -k tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-aggregated/vllm          # or: kubectl delete namespace dynamo-agg-vllm
```

This removes every object in the namespace. The model and compile caches on the nodes (`/data/nemotron-ultra/...`) remain, and the node labels stay for the next track.

## Troubleshooting

| Symptom | Check |
|---|---|
| Pod `Pending` | `kubectl describe pod`: node label present? 8 free GPUs? A taint that needs a toleration? |
| Worker exits with `Checkpoint revision mismatch` | `/data/nemotron-ultra/model/DEPLOYED_REVISION` differs between nodes or is missing ([prerequisites §6](../../../../../../platform/prerequisites/#6-download-the-model-on-both-nodes)) |
| `/v1/models` is empty | Workers not registered yet, or cannot reach etcd. Check the worker logs for etcd errors and `kubectl -n dynamo-agg-vllm get svc etcd`. |
| Worker IP looks wrong in logs | `kubectl get nodes -o wide`: InternalIP must be the private IP ([prerequisites §7](../../../../../../platform/prerequisites/#kubernetes-path)) |

More in [reference/troubleshooting.md](../../../../../../reference/troubleshooting.md).
