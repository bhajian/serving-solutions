# 03-planner-demo: Planner adjusts the P:D layout against the SLO

[Home](../../../../../README.md) › [Tracks](../../../../README.md) › [NVIDIA Dynamo](../../../README.md) › [Studies](../../README.md) › [Planned](../README.md) › 03-planner-demo

> **UNVALIDATED — scheduled.** Prepared offline; nothing in this folder has been run. The
> duration is a planning estimate, not a measurement.

**Objective.** Profile the disaggregated graph (DynamoGraphDeploymentRequest, thorough), then step the arrival rate and show the Planner changing prefill/decode replicas to hold the SLO.

**Hypothesis.** With SLA mode, mean targets TTFT 1 s / ITL 25 ms (from p99 2 s / 40 ms) and a 16-GPU budget, the Planner adds decode replicas as load rises and returns them as it falls, keeping goodput attainment above 90% at loads where a fixed 1P:3D layout misses the SLO.

## Layouts

Uses the production overlays in tracks/nvidia-dynamo/production (no per-experiment layouts).

## Dataset

```bash
python -m benchmarks.generate_dataset --workload chatbot --sessions 6000 --turns 1 --isl-dist lognormal:4000:0.6:2000:16000 --osl-dist lognormal:512:0.6:256:2048 --max-model-len 262144 --seed 20261002 --tokenizer build/nemotron-128k/tokenizer --template-kwargs '{"enable_thinking":false}' --out datasets/generated/nemotron-realistic-6000.jsonl
```

## Run

```bash
kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/production/nemotron-3-nano-h200/profiling
kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano wait --for=jsonpath='{.status.phase}'=Ready dynamographdeploymentrequest/nemotron-3-nano-profile --timeout=6h
kubectl --context "$KUBE_CONTEXT" apply -k build/site/tracks/nvidia-dynamo/production/nemotron-3-nano-h200/disaggregated
# Step load: 10 min each at 2, 4, 8, 12, 8, 4, 2 sessions/s; record replicas every 30 s
(while sleep 30; do kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano get dynamographdeployment nemotron-3-nano \
   -o jsonpath='{.metadata.generation} {range .spec.components[*]}{.name}={.replicas} {end}{"\n"}'; done) > build/experiments/03-planner-demo/replicas.log &
for rps in 2 4 8 12 8 4 2; do
  kubectl --context "$KUBE_CONTEXT" -n nemotron-3-nano exec benchmark-client -c client -- python3 -m benchmarks.loadgen \
    --base-url http://nemotron-3-nano-frontend.nemotron-3-nano.svc.cluster.local:8000/v1 --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 --technology dynamo-disagg-k8s \
    --dataset /bench/nemotron-realistic-6000.jsonl --max-model-len 262144 --arrival poisson --rps $rps --duration 600 \
    --slo-ttft-ms 2000 --slo-itl-ms 40 --gpu-count 16 --label planner-step-$rps --results /bench/results/03-planner-demo
done
```

## Success criteria

- The profiling request reaches `Ready` and its PVC holds `selected_prefill_interpolation/raw_data.npz` and the decode equivalent.
- The replicas log shows at least one scale-up and one scale-down that follow the load steps.
- Per-step goodput attainment is reported next to the replica counts; the result states whether the Planner held the SLO.

**Planning estimate:** profiling 2-4 h (operator-run Job) + 7 load steps x 10 min = ~4 h. See [READY.md](READY.md) before starting.
