# 06-overlap-scheduling: Overlap scheduling for hybrid Mamba (Nemotron 3 Nano)

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 06-overlap-scheduling

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Measure what disabling overlap scheduling costs on Nemotron-H.

**Hypothesis.** SGLang 0.5.16 forces overlap scheduling off with the measured `no_buffer` Mamba strategy (arg_groups/overrides.py L1158-1201). `extra_buffer` allows overlap for NemotronH with the triton linear-attention backend and should lower TPOT at moderate batch sizes, at the cost of extra Mamba state memory.

## Layouts

| Config | Topology | Coordinates |
| --- | --- | --- |
| `no-buffer-overlap-off` | aggregated | `{'mode': 'agg', 'mamba': 'no_buffer', 'overlap': False}` |
| `extra-buffer-overlap-on` | aggregated | `{'mode': 'agg', 'mamba': 'extra_buffer', 'overlap': True}` |

## Dataset

```bash
python -m benchmarks.generate_dataset --workload chatbot --sessions 6000 --turns 1 --isl-dist lognormal:4000:0.6:2000:16000 --osl-dist lognormal:512:0.6:256:2048 --max-model-len 262144 --seed 20261002 --tokenizer build/nemotron-128k/tokenizer --template-kwargs '{"enable_thinking":false}' --out datasets/generated/nemotron-realistic-6000.jsonl
```

## Run

```bash
python -m benchmarks.sweep run tracks/nvidia-dynamo/studies/planned/06-overlap-scheduling/sweep.yaml --context "$KUBE_CONTEXT" --exec-pod nemotron-3-nano/benchmark-client
```

## Success criteria

- Worker logs confirm the effective strategy and overlap state.
- TPOT p50/p99 and goodput per config at equal RPS; Mamba memory (`sglang:mamba_usage`) reported.

**Planning estimate:** 2 configs x 3 RPS x 8 min + 2 layout changes = ~1 h. See [READY.md](READY.md) before starting.

The `--disable-overlap-schedule` flag is removed by the generator for `extra-buffer-overlap-on`.
