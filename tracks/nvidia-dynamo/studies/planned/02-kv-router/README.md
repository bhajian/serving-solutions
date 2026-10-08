# 02-kv-router: KV router balance and prefix hit rate against round-robin

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 02-kv-router

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Confirm the KV-router configuration fixes the 152/120/120/120 imbalance and measure its prefix-reuse benefit against round-robin.

**Hypothesis.** With unique prompts, the weighted KV router (active-request weight, waiting for all workers) spreads a 512-request burst within ±2 requests per worker, while the default KV router can repeat the imbalance. With multi-turn prefix reuse, the KV router reaches a higher engine cache hit rate and lower follow-up TTFT than round-robin.

## Layouts

| Config | Topology | Coordinates |
| --- | --- | --- |
| `kv-weighted` | aggregated | `{'mode': 'agg', 'router': 'kv-weighted'}` |
| `kv-default` | aggregated | `{'mode': 'agg', 'router': 'kv-default'}` |
| `round-robin` | aggregated | `{'mode': 'agg', 'router': 'round-robin'}` |

## Dataset

```bash
python -m benchmarks.generate_dataset --workload chatbot --sessions 1500 --isl-dist lognormal:6000:0.5:2000:16000 --osl-dist lognormal:384:0.5:128:1024 --max-model-len 262144 --seed 20261003 --tokenizer build/nemotron-128k/tokenizer --template-kwargs '{"enable_thinking":false}' --out datasets/generated/nemotron-reuse-1500.jsonl
# Burst balance check: reuse the 8K/128K dataset (512 unique single-turn sessions).
```

## Run

```bash
# Balance: a 512-request closed-loop burst per router, 2,048 forced output tokens
python -m benchmarks.long_decode --base-url http://nemotron-3-nano-frontend.nemotron-3-nano.svc.cluster.local:8000/v1 --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 \
  --technology dynamo-agg-k8s --dataset /bench/nemotron-3-nano-chatbot-8k-512.jsonl --sessions 512 \
  --concurrency 512 --max-model-len 262144 --min-input-tokens 8000 --output-tokens 2048 --label burst
# Prefix reuse: open-loop multi-turn sessions
python -m benchmarks.sweep run tracks/nvidia-dynamo/studies/planned/02-kv-router/sweep.yaml --context "$KUBE_CONTEXT" --exec-pod nemotron-3-nano/benchmark-client
```

## Success criteria

- Burst: per-worker request counts (from `decode_worker_id`) within ±2 of 128 for `kv-weighted` in three bursts.
- Reuse: `sglang:cache_hit_rate` and `dynamo_component_router_kv_hit_rate` reported per router; follow-up TTFT p50/p99 compared at equal goodput.

**Planning estimate:** 3 routers x (burst ~3 min + 3 RPS x 8 min) + 3 layout changes x ~5 min = ~1.6 h. See [READY.md](READY.md) before starting.
