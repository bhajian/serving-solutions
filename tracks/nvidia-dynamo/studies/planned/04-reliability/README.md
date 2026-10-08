# 04-reliability: Confirm the reliability mitigations

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 04-reliability

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Measure each mitigation from reference/troubleshooting.md against its unmitigated form.

**Hypothesis.** (a) `--gc-threshold 7000 10 100` cuts generation-2 GC pauses per worker by ~100x and ITL p99.9 from ~500 ms towards the decode step time; `gc.freeze()` after warmup shortens the remaining pauses. (b) A prefill cap of 32 keeps prefill host memory well under the 448Gi limit in a 384-request burst, where 136 peaked at 308 GiB. (c) The frontend probe restarts a frontend whose discovery lost every worker. (d) `--disable-radix-cache` removes the ~37 s end-of-run freeze on aggregated workers.

## Layouts

| Config | Topology | Coordinates |
| --- | --- | --- |
| `gc-default` | disaggregated | `{'mode': 'disagg', 'gc': 'python-default'}` |
| `gc-threshold` | disaggregated | `{'mode': 'disagg', 'gc': 'threshold'}` |
| `gc-threshold-freeze` | disaggregated | `{'mode': 'disagg', 'gc': 'threshold+freeze'}` |
| `prefill-cap-136` | disaggregated | `{'mode': 'disagg', 'prefill_cap': 136}` |
| `agg-radix-on` | aggregated | `{'mode': 'agg', 'radix': True}` |
| `agg-radix-off` | aggregated | `{'mode': 'agg', 'radix': False}` |

## Dataset

```bash
# GC and memory: the 8K/128K dataset (datasets/generated/nemotron-3-nano-chatbot-8k-512.jsonl), 384 requests, 24,576 forced output tokens
# Radix: the same dataset, 512 requests, 131,072 forced output tokens (the recorded wave)
```

## Run

```bash
# (a) GC: per config, a 384-request wave with 24,576 output tokens; count GC warnings in worker logs
for c in gc-default gc-threshold gc-threshold-freeze; do
  kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/studies/planned/04-reliability/configs/$c
  kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano wait --for=condition=Ready dynamographdeployment/nemotron-3-nano --timeout=60m
  kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano exec benchmark-client -c client -- python3 -m benchmarks.long_decode \
    --base-url http://nemotron-3-nano-frontend.nemotron-3-nano.svc.cluster.local:8000/v1 --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 --technology dynamo-disagg-k8s \
    --dataset /bench/nemotron-3-nano-chatbot-8k-512.jsonl --sessions 384 --concurrency 384 --max-model-len 262144 \
    --min-input-tokens 8000 --output-tokens 24576 --label gc-$c --results /bench/results/04-reliability
  kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano logs -l nvidia.com/dynamo-component-type=decode --since=1h | grep -c "LONG GARBAGE"
done
# (b) Prefill memory: sample anonymous memory every 5 s during the same wave on prefill-cap-136 and gc-threshold (cap 32)
python tracks/nvidia-dynamo/studies/planned/04-reliability/sample_memory.py --context "$KUBE_CONTEXT" --namespace nemotron-3-nano --role prefill --out build/experiments/04-reliability/prefill-memory.csv
# (c) Discovery loss: delete all prefill pods, confirm frontend readiness drops, liveness restarts after 300 s if they do not return
kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano delete pod -l nvidia.com/dynamo-component-type=prefill
kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano get pods -l nvidia.com/dynamo-component-type=frontend -w
# (d) Radix: the recorded 512 x 131,072-token wave once with agg-radix-on and once with agg-radix-off
```

## Success criteria

- (a) GC warnings per worker-hour and ITL p99.9 reported per config; the mitigation is kept only if p99.9 improves without a TPOT regression.
- (b) Peak prefill anonymous memory per cap, against the 448Gi limit; the allocator identified from `/proc/<pid>/smaps` of the scheduler processes.
- (c) Readiness false within 30 s of losing all prefill workers; recovery or restart recorded with timestamps.
- (d) Worst ITL per run; the freeze is attributed to the radix cache only if it disappears with `agg-radix-off`.

**Planning estimate:** (a) 3 x ~25 min, (b) shares (a), (c) ~20 min, (d) 2 x ~35 min: ~3 h. See [READY.md](READY.md) before starting.
