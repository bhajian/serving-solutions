# 08-resilience-soak: Failure injection and 24 h soak

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 08-resilience-soak

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Measure impact and recovery time when a decode worker, the prefill worker or a frontend is killed, then run 24 h of steady load watching memory growth, transfer errors and XIDs.

**Hypothesis.** With two frontends, losing one costs only its in-flight streams. Losing the prefill worker stops new requests (no aggregated fallback in PD mode) until it re-registers. Losing one of three decode workers costs its in-flight requests and a third of decode capacity until restart. No resource grows without bound over 24 h.

## Layouts

Uses the production overlays in tracks/nvidia-dynamo/production (no per-experiment layouts).

## Dataset

```bash
python -m benchmarks.generate_dataset --workload chatbot --sessions 6000 --turns 1 --isl-dist lognormal:4000:0.6:2000:16000 --osl-dist lognormal:512:0.6:256:2048 --max-model-len 262144 --seed 20261002 --tokenizer build/nemotron-128k/tokenizer --template-kwargs '{"enable_thinking":false}' --out datasets/generated/nemotron-realistic-6000.jsonl
```

## Run

```bash
# Steady open-loop load at 50% of the best goodput from experiment 01, then, 15 min apart:
tracks/nvidia-dynamo/studies/planned/08-resilience-soak/inject.sh decode
tracks/nvidia-dynamo/studies/planned/08-resilience-soak/inject.sh prefill
tracks/nvidia-dynamo/studies/planned/08-resilience-soak/inject.sh frontend
# Soak: 24 h at the same load; export Prometheus ranges for prefill/decode RSS, sglang:kv_transfer_*,
# node_infiniband_*_errors, DCGM_FI_DEV_XID_ERRORS and dynamo_frontend_requests_total{status="error"}
```

## Success criteria

- Per injected failure: failed requests, time to readiness and time to first successful request after recovery.
- Soak: RSS slope per worker (GiB/h), total transfer errors, XIDs and 5xx rate; any unbounded growth is a finding.

**Planning estimate:** failure injection ~1.5 h; soak 24 h. See [READY.md](READY.md) before starting.
