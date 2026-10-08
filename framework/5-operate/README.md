# 5 · Operate

[Home](../../README.md) › [Framework](../README.md) › 5 · Operate

**Output:** a runbook and a list of re-validation triggers. **Gate:** none; this stage loops
back to stage 4 whenever a trigger fires. Background:
[blueprint 10](../../blueprint/10-production-operations.md).

## What to watch

| Signal | Why | Track 1 (Dynamo) | Track 2 (llm-d) |
| --- | --- | --- | --- |
| TTFT and ITL p99 per pool | The SLO itself; a single blended number hides which pool to scale | [observability](../../tracks/nvidia-dynamo/observability/README.md) | vLLM `/metrics`, router `llm_d_epp_*` |
| Queue depth, running requests | Saturation before latency moves | Frontend and worker metrics | Router in-flight requests and tokens per pod |
| KV cache usage and prefix hit rate | Whether routing still finds the cache | Engine metrics, KV router hit rate | `vllm:prefix_cache_*`, router prefix indexer hit ratio |
| KV transfer errors and latency (P/D) | Silent recompute or failed handoffs | NIXL / worker metrics | Routing sidecar and vLLM connector metrics |
| Worker discovery | A frontend that lost its workers still answers `/health` | Discovery-aware probe ([common](../../tracks/nvidia-dynamo/common/README.md)) | InferencePool endpoints seen by the router |

## Re-validation triggers

Re-run the acceptance study (L2) when any of these change: model revision or precision,
engine or image digest, router or scheduler configuration, worker layout, node type or
driver, or a measured traffic shift (ISL, OSL or reuse moving out of the profile's range).

## Change practice

- Pin images by digest and models by revision; verify both at startup.
- Change one layer at a time, then re-validate.
- Keep a measured baseline per deployment; compare against it, not against vendor numbers.
- Known failure modes and fixes: [reference/troubleshooting.md](../../reference/troubleshooting.md).
