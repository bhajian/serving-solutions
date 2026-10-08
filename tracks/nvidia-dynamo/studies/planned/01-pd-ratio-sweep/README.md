# 01-pd-ratio-sweep: P:D ratio and per-role TP on 16 H200 GPUs, goodput at SLO

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 01-pd-ratio-sweep

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Find where disaggregation wins on this site: TP2/TP4 prefill with 2-6 decode workers against 4 x TP4 and 8 x TP2 aggregated replicas, under open-loop Poisson arrivals with realistic ISL/OSL.

**Hypothesis.** The recorded studies only compared 1P:1D (prefill-bound, halved prefill capacity) and 1P:3D (idle prefill on a decode-bound wave). With ISL 2-16K and OSL 256-2K, both phases matter. A 2 x TP2 prefill pool with 3 x TP4 or 6 x TP2 decode keeps prefill out of the decode batch (the 13 s aggregated stalls) and should sustain higher goodput at p99 ITL 40 ms than aggregated at the same offered load. At low load, aggregated should win on TTFT.

## Layouts

| Config | Topology | Coordinates |
| --- | --- | --- |
| `agg-4x-tp4` | aggregated | `{'mode': 'agg', 'workers': 4, 'tp': 4}` |
| `agg-8x-tp2` | aggregated | `{'mode': 'agg', 'workers': 8, 'tp': 2}` |
| `pd-1x-tp4-3x-tp4` | disaggregated | `{'mode': 'disagg', 'prefill': 1, 'tp_prefill': 4, 'decode': 3, 'tp_decode': 4}` |
| `pd-2x-tp2-3x-tp4` | disaggregated | `{'mode': 'disagg', 'prefill': 2, 'tp_prefill': 2, 'decode': 3, 'tp_decode': 4}` |
| `pd-2x-tp2-6x-tp2` | disaggregated | `{'mode': 'disagg', 'prefill': 2, 'tp_prefill': 2, 'decode': 6, 'tp_decode': 2}` |
| `pd-2x-tp4-2x-tp4` | disaggregated | `{'mode': 'disagg', 'prefill': 2, 'tp_prefill': 4, 'decode': 2, 'tp_decode': 4}` |

## Dataset

```bash
python -m benchmarks.generate_dataset --workload chatbot --sessions 6000 --turns 1 --isl-dist lognormal:4000:0.6:2000:16000 --osl-dist lognormal:512:0.6:256:2048 --max-model-len 262144 --seed 20261002 --tokenizer build/nemotron-128k/tokenizer --template-kwargs '{"enable_thinking":false}' --out datasets/generated/nemotron-realistic-6000.jsonl
```

## Run

```bash
python -m benchmarks.sweep plan tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/sweep.yaml
python -m benchmarks.sweep run tracks/nvidia-dynamo/studies/planned/01-pd-ratio-sweep/sweep.yaml --context "$KUBE_CONTEXT" --exec-pod nemotron-3-nano/benchmark-client
python -m benchmarks.sweep table tracks/nvidia-dynamo/studies/01-pd-ratio-sweep
```

## Success criteria

- Every run: 0 failed and 0 invalid requests; client start lag p99 < 100 ms (otherwise the client was the bottleneck).
- For each configuration, the highest offered RPS with `run_meets_slo` and its goodput are reported.
- The result states which configuration has the highest goodput at SLO, and at which load aggregated and disaggregated cross over. A result where aggregated wins everywhere is a valid outcome.

**Planning estimate:** 6 configs x 6 RPS levels x 8 min + 6 layout changes x ~15 min = ~6.3 h; run the four rows marked core first (~4 h). See [READY.md](READY.md) before starting.

Core rows, in order: `agg-4x-tp4`, `pd-1x-tp4-3x-tp4`, `pd-2x-tp2-3x-tp4`, `pd-2x-tp2-6x-tp2`.
The RPS levels are planning values. Run the first level of `agg-4x-tp4` as a pilot; if goodput already saturates there, rescale the list in sweep.yaml.
