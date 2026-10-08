# Disaggregated serving · Dynamo + vLLM · Docker Compose

[Home](../../../../../../README.md) › [Tracks](../../../../../README.md) › [NVIDIA Dynamo](../../../../README.md) › [Sites](../../../README.md) › [hgx-b300-2x8](../../README.md) › [Compose](../README.md) › Docker Compose

Deploy with Docker Compose on the GPU servers themselves. Compose manages containers **locally**: you run `node-a.yaml` on Node A and `node-b.yaml` on Node B. Compose is not a cross-host scheduler.

## What you deploy

| Node | Containers | GPUs |
|---|---|---|
| A | `etcd`, `frontend` (API :8000), **`prefill`** | 8 (prefill) |
| B | **`decode`** | 8 (decode) |

The prefill worker on Node A builds the KV cache; it moves to the decode worker on Node B over InfiniBand.

## Files in this folder

| File | Purpose |
|---|---|
| [node-a.yaml](node-a.yaml) | Node A services. Every engine flag is written out and commented. |
| [node-b.yaml](node-b.yaml) | Node B service |
| [deployment.json](deployment.json) | Run record passed to the benchmark (`--deployment`), so results record what was deployed |

Site-specific values (IPs, interface, InfiniBand devices, paths) come from `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env`. The Compose files use no other variables.

## Before you start

- [ ] [00 · Prerequisites](../../../../../../platform/prerequisites/) done: drivers, RDMA test, model downloaded to the same path on both nodes.
- [ ] `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env` created from `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env.example` on every node you use ([prerequisites §7](../../../../../../platform/prerequisites/#docker-path)).
- [ ] No other track is running. Every track uses all 8 GPUs per node and the same host ports. Stop the previous one with its `down` command.
- [ ] All commands below run **from the repository root** on the node named in each step.

## Step 1 · Check the files and pull the images

**Each node**, for its own file:

```bash
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml config -q   # Node A: syntax + variables resolve
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-b.yaml config -q   # Node B
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml pull        # Node A
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-b.yaml pull        # Node B
```

`config` (without `-q`) prints the fully resolved file, so you can confirm the IPs came from `tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env`.

## Step 2 · Start etcd (Node A)

```bash
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml up -d etcd
source tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env && curl -fsS http://$NODE_A_IP:2379/health     # expect {"health":"true"}
```

Run the same `curl` on Node B. If it fails there, fix routing or the firewall before continuing. Continue only when etcd is healthy.

## Step 3 · Start the frontend and the prefill worker (Node A)

```bash
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml up -d frontend prefill
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml logs -f prefill     # Ctrl+C stops following, not the container
```

## Step 4 · Start the decode worker (Node B)

**Node B:** start the decode worker. Node B needs Node A's etcd to be healthy first.

```bash
source tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env && curl -fsS http://$NODE_A_IP:2379/health
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-b.yaml up -d
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-b.yaml logs -f decode
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

If `/v1/models` returns `"data":[]` after the workers report ready, read the frontend logs: `docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml logs frontend`.

## Step 7 · Prove the KV cache really moves over InfiniBand

A `200 OK` shows that the model answers. It does **not** show that decode used a KV cache transferred from prefill over RDMA. Check all three of these:

1. **Logs:** look for the NIXL/UCX initialization lines, which name the `mlx5_*` devices from `IB_DEVICES`. Also look for transfer errors, which should be absent.

   ```bash
   docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml logs prefill | grep -Ei 'nixl|ucx|transfer' | tail
   docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-b.yaml logs decode  | grep -Ei 'nixl|ucx|transfer' | tail   # on Node B
   ```

2. **Metrics under load:** send a prompt of several thousand tokens (the quick benchmark in step 8 does this), then read transfer counters on both workers:

   ```bash
   curl -s http://<node-a-ip>:8081/metrics | grep -Ei 'nixl|transfer|kv' | head -20
   curl -s http://<node-b-ip>:8081/metrics | grep -Ei 'nixl|transfer|kv' | head -20
   ```

3. **Fabric counters:** on either node, the InfiniBand port counters should rise during long prompts:

   ```bash
   cat /sys/class/infiniband/mlx5_4/ports/1/counters/port_xmit_data   # repeat, compare
   ```

Metric names vary between versions. An empty `grep` alone does not prove failure, but rising IB counters together with successful long-prompt responses do prove success.

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
  --base-url http://${NODE_A_IP}:8000/v1 \
  --model nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4 \
  --technology dynamo-disagg-compose \
  --deployment tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/deployment.json \
  --dataset datasets/generated/nemotron-chatbot-8k.jsonl \
  --max-model-len 32768 --output-tokens 256 --concurrency 4
```

Each request prints `TTFT=...ms`. The run ends with `Results: tracks/nvidia-dynamo/studies/<run-id>/`, which contains `summary.csv` with TTFT, TPOT, ITL and throughput percentiles. Use **the same dataset file** on every track, then compare them side by side in [benchmarks/README.md](../../../../../../benchmarks/README.md).

## Stop and clean up

Stop **Node B first, then Node A**:

```bash
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-b.yaml down      # Node B
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/02-dynamo-disagg-vllm/node-a.yaml down      # Node A
```

`down` keeps the model, the caches under `RUNTIME_DIR/disagg-vllm/` and the etcd volume. Do not add `-v` for a routine switch. Always stop **both** workers before changing the model, context length, image or engine, because a partial restart can pair incompatible workers.

## Troubleshooting

See [reference/troubleshooting.md](../../../../../../reference/troubleshooting.md). The most common problems are an etcd address that is unreachable from Node B, the model missing from `/v1/models` (check the frontend logs), and a request that stalls after prefill (check the NIXL/UCX devices and RDMA access).
