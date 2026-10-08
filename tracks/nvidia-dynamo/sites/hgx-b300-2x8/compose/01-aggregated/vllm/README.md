# Aggregated serving · Dynamo + vLLM · Docker Compose

[Home](../../../../../../../README.md) › [Tracks](../../../../../../README.md) › [NVIDIA Dynamo](../../../../../README.md) › [Sites](../../../../README.md) › [hgx-b300-2x8](../../../README.md) › [Compose](../../README.md) › [01-aggregated](../README.md) › Docker Compose

Deploy with Docker Compose on the GPU servers themselves. Compose manages containers **locally**: you run `node-a.yaml` on Node A and `node-b.yaml` on Node B. Compose is not a cross-host scheduler.

## What you deploy

| Node | Containers | GPUs |
|---|---|---|
| A | `etcd`, `frontend` (API :8000), `worker` | 8 |
| B (optional) | `worker` (second replica) | 8 |

Each `worker` is a complete replica that runs prefill and decode. **Single-node lab:** skip every Node B step.

## Files in this folder

| File | Purpose |
|---|---|
| [node-a.yaml](node-a.yaml) | Node A services. Every engine flag is written out and commented. |
| [node-b.yaml](node-b.yaml) | Node B service |
| [deployment.json](deployment.json) | Run record passed to the benchmark (`--deployment`), so results record what was deployed |

Site-specific values (IPs, interface, InfiniBand devices, paths) come from `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env`. The Compose files use no other variables.

## Before you start

- [ ] [00 · Prerequisites](../../../../../../../platform/prerequisites/) done: drivers, model downloaded to the same path on every node you use.
- [ ] `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env` created from `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env.example` on every node you use ([prerequisites §7](../../../../../../../platform/prerequisites/#docker-path)).
- [ ] No other track is running. Every track uses all 8 GPUs per node and the same host ports. Stop the previous one with its `down` command.
- [ ] All commands below run **from the repository root** on the node named in each step.

## Step 1 · Check the files and pull the images

**Each node**, for its own file:

```bash
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-a.yaml config -q   # Node A: syntax + variables resolve
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-b.yaml config -q   # Node B
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-a.yaml pull        # Node A
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-b.yaml pull        # Node B
```

`config` (without `-q`) prints the fully resolved file, so you can confirm the IPs came from `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env`.

## Step 2 · Start etcd (Node A)

```bash
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-a.yaml up -d etcd
source tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env && curl -fsS http://$NODE_A_IP:2379/health     # expect {"health":"true"}
```

Continue only when etcd is healthy.

## Step 3 · Start the frontend and the worker (Node A)

```bash
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-a.yaml up -d frontend worker
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-a.yaml logs -f worker     # Ctrl+C stops following, not the container
```

## Step 4 · Start the second worker (Node B)

**Node B (optional second replica):**

```bash
source tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env && curl -fsS http://$NODE_A_IP:2379/health
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-b.yaml up -d
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-b.yaml logs -f worker
```

## Step 5 · Wait for initialization

Loading the ~352 GB checkpoint and compiling kernels takes a while (tens of minutes on first start; caches make restarts faster). Wait for `VllmWorker ... has been initialized` and `Registered base model` in the **current** startup's logs.

Workers deliberately have **no restart policy**, so a failed start stays visible. Check with `docker compose ... ps -a` and read the logs if a container exited. `up -d` returning is not a readiness check.

## Step 6 · Verify the API

From any machine in the private network:

```bash
source tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env
curl -fsS http://$NODE_A_IP:8000/v1/models            # must list nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4
curl -fsS http://$NODE_A_IP:8081/health               # Node A worker
curl -fsS http://$NODE_B_IP:8081/health               # Node B worker
curl --fail-with-body -sS --max-time 300 http://$NODE_A_IP:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4",
       "messages":[{"role":"user","content":"Explain prefill and decode in three sentences."}],
       "max_tokens":256,"temperature":0,
       "chat_template_kwargs":{"enable_thinking":false,"force_nonempty_content":true}}'
```

If `/v1/models` returns `"data":[]` after the workers report ready, read the frontend logs: `docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-a.yaml logs frontend`.

## Step 7 · Watch the router balance the replicas

With two replicas, send the same long prompt twice and a different one once. The KV-aware router should send the repeat to the replica that already caches its prefix. Look at the frontend logs for routing decisions and at each worker's prefix-cache metrics:

```bash
curl -s http://${NODE_A_IP}:8081/metrics | grep -Ei 'prefix|cache_hit|kv' | head
curl -s http://${NODE_B_IP}:8081/metrics | grep -Ei 'prefix|cache_hit|kv' | head
```

Metric names vary between versions. What matters is that both workers receive traffic and repeated prefixes produce cache hits.

## Step 8 · See the results

Run a small, repeatable benchmark from any machine that has the benchmark virtualenv ([prerequisites §2](../../../../../../../platform/prerequisites/#2-software)) and the model's tokenizer files. Node A works.

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
  --base-url http://${NODE_A_IP}:8000/v1 \
  --model nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4 \
  --technology dynamo-agg-compose \
  --deployment tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/deployment.json \
  --dataset datasets/generated/nemotron-chatbot-8k.jsonl \
  --max-model-len 32768 --output-tokens 256 --concurrency 4
```

Each request prints `TTFT=...ms`. The run ends with `Results: tracks/nvidia-dynamo/studies/<run-id>/`, which contains `summary.csv` with TTFT, TPOT, ITL and throughput percentiles. Use **the same dataset file** on every track, then compare them side by side in [benchmarks/README.md](../../../../../../../benchmarks/README.md).

## Stop and clean up

Stop **Node B first, then Node A**:

```bash
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-b.yaml down      # Node B
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/01-aggregated/vllm/node-a.yaml down      # Node A
```

`down` keeps the model, the caches under `RUNTIME_DIR/agg-vllm/` and the etcd volume. Do not add `-v` for a routine switch. Always stop **both** workers before changing the model, context length, image or engine, because a partial restart can pair incompatible workers.

## Troubleshooting

See [reference/troubleshooting.md](../../../../../../../reference/troubleshooting.md). The most common problems are an etcd address that is unreachable from Node B, the model missing from `/v1/models` (check the frontend logs), and a GPU that another container still holds (`nvidia-smi`).
