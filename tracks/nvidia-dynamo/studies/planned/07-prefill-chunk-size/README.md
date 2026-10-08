# 07-prefill-chunk-size: Prefill chunk size at 128K context

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 07-prefill-chunk-size

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Measure TTFT and decode interference for 4096, 8192 and 16384-token prefill chunks at 128K input.

**Hypothesis.** Larger chunks lower TTFT for 128K prompts (fewer scheduler iterations) but lengthen each decode stall in aggregated mode; 8192 should be the better trade-off for this model.

## Layouts

| Config | Topology | Coordinates |
| --- | --- | --- |
| `chunk-4096` | aggregated | `{'mode': 'agg', 'chunked_prefill': 4096}` |
| `chunk-8192` | aggregated | `{'mode': 'agg', 'chunked_prefill': 8192}` |
| `chunk-16384` | aggregated | `{'mode': 'agg', 'chunked_prefill': 16384}` |

## Dataset

```bash
# The recorded 128K dataset (datasets/generated/nemotron-3-nano-chatbot-128k-32.jsonl), plus a concurrent short-prompt stream to expose decode stalls.
```

## Run

```bash
for c in chunk-4096 chunk-8192 chunk-16384; do
  kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/studies/planned/07-prefill-chunk-size/configs/$c
  kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano wait --for=condition=Ready dynamographdeployment/nemotron-3-nano --timeout=60m
  # 128K replay at concurrency 4 (as recorded) while loadgen sends 1 rps of short requests
done
```

## Success criteria

- First-turn TTFT for 128K prompts per chunk size; ITL p99/p99.9 of the concurrent short stream.

**Planning estimate:** 3 configs x ~25 min = ~1.3 h. See [READY.md](READY.md) before starting.
