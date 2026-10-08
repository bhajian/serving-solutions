# 05-deepseek-layout: DeepSeek V4 Pro: DP attention + EP, MTP, MoE backend, PD prefix reuse

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 05-deepseek-layout

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Compare the measured TP8 layout with MTP (EAGLE with the NextN head) and DP attention with expert parallelism, and find out why the 256K disaggregated run showed no prefix reuse.

**Hypothesis.** MTP lowers TPOT at low concurrency (SGLang 0.5.16 allows only EAGLE with topk 1 or DSPARK for DeepSeek V4: arg_groups/deepseek_v4_hook.py). DP attention + EP8 raises decode throughput at higher concurrency by removing attention TP all-reduces. Decode-side radix caching in PD mode restores follow-up hits. TODO(verify-upstream): upstream 1.4.0 recipes run V4 Pro only as TP8, so DP attention for V4 on H200 and alternatives to Marlin for its MXFP4 MoE weights on Hopper are unconfirmed.

## Layouts

| Config | Topology | Coordinates |
| --- | --- | --- |
| `tp8-marlin` | aggregated | `{'mode': 'agg', 'layout': 'tp8', 'moe': 'marlin'}` |
| `tp8-marlin-mtp` | aggregated | `{'mode': 'agg', 'layout': 'tp8', 'moe': 'marlin', 'mtp': 'eagle-nextn'}` |
| `dp8-attn-ep8` | aggregated | `{'mode': 'agg', 'layout': 'dp-attention+ep', 'moe': 'marlin'}` |
| `pd-tp8-decode-radix` | disaggregated | `{'mode': 'disagg', 'decode_radix': True}` |

## Dataset

```bash
# The 256K agentic dataset (tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison/REPORT.md) and a
# realistic ISL/OSL dataset generated with the DeepSeek V4 encoder (--deepseek-v4-encoder).
```

## Run

```bash
for c in tp8-marlin tp8-marlin-mtp dp8-attn-ep8 pd-tp8-decode-radix; do
  kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/studies/planned/05-deepseek-layout/configs/$c
  kubectl --context "$KUBE_CONTEXT" -n deepseek-v4-pro wait --for=condition=Ready dynamographdeployment/deepseek-v4-pro --timeout=90m
  # closed loop at concurrency 1, 4, 16 with realistic ISL/OSL; then the 256K replay for pd-tp8-decode-radix
done
```

## Success criteria

- Each config starts, or its startup error is recorded as the finding.
- TPOT and output tokens/s at concurrency 1/4/16, MTP acceptance (`sglang:spec_accept_length`).
- Follow-up cache hits in PD mode with `--disaggregation-decode-enable-radix-cache`, compared with the 256K record.

**Planning estimate:** 4 configs x (load ~40 min, warm start ~20 min) = ~4 h. See [READY.md](READY.md) before starting.
