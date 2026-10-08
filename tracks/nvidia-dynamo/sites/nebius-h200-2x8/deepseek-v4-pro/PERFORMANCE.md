# Performance testing DeepSeek V4 Pro

The completed [256K comparison](../../../studies/deepseek-v4-pro-256k-comparison/REPORT.md) has a dedicated notebook.
The cluster is now aggregated. The 8K disaggregated workflow below requires first
applying `40-workers-disaggregated.yaml` and waiting for both workers, as described
in the deployment README. Use the matching `deployment-disaggregated.json`.

The comparison notebook **reads results; it does not generate load**. Run the CLI
sweep first, then open `benchmarks/compare.ipynb` with the repository `.venv` kernel.
The current target is `http://<LOADBALANCER_IP>:8000/v1`: DeepSeek V4 Pro, one TP8
prefill worker plus one TP8 decode worker, 262,144 context, four concurrent requests
per role, non-thinking mode. No model download is needed when switching topology.

## 1. Prepare a larger dataset

Run from the repository root. The 64-session chatbot file below has already been
generated in this workspace. Reuse it; the generator refuses to overwrite files.
For a fresh checkout, follow the deployment README's small tokenizer download
step, then run:

```bash
source .venv/bin/activate
python -m benchmarks.generate_dataset --workload chatbot --sessions 64 \
  --input-tokens 8000 --output-tokens 256 --max-model-len 262144 \
  --tokenizer build/deepseek-v4-pro-tokenizer \
  --deepseek-v4-encoder build/deepseek-v4-pro-tokenizer/encoding/encoding_dsv4.py \
  --trust-remote-code --template-kwargs '{"thinking":false}' \
  --out datasets/generated/deepseek-v4-pro-chatbot-8k-64.jsonl
```

Each session has three turns: 192 measured requests per run. The output budget
is a maximum, not a forced output length. Inspect actual completion lengths.
Agentic replay can be generated with `--workload agentic` and a distinct output
filename; run it separately with the same settings.

## 2. Run the load sweep

Use a dedicated results directory so earlier correctness tests do not enter the
performance report. Avoid other inference traffic while measuring.

```bash
source .venv/bin/activate
export PERF_RESULTS="$PWD/results/deepseek-v4-pro-disagg-8k"
CONCURRENCIES='1 2 4 8 16' REPETITIONS=3 bash tools/sweep.sh \
  --base-url http://<LOADBALANCER_IP>:8000/v1 \
  --model deepseek-ai/DeepSeek-V4-Pro-0813 \
  --technology dynamo-disagg-k8s \
  --deployment tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/lab/as-measured/records/deployment-disaggregated.json \
  --dataset datasets/generated/deepseek-v4-pro-chatbot-8k-64.jsonl \
  --max-model-len 262144 --min-input-tokens 8000 --output-tokens 256 \
  --warmup 4 --cache-state uncontrolled --results "$PERF_RESULTS"
```

This runs 15 measurements / 2,880 measured requests, plus short warmups. The sweep
stops on errors or invalid measurements. For a quick pilot, use
`CONCURRENCIES='1 4' REPETITIONS=1` and a different results folder. Do not mix the
pilot into the final repeated series.

The runner defaults to closed-loop sessions with one in-flight turn per session.
Four reaches the configured per-worker request limit; concurrency 8 and 16
intentionally measure queueing. The context window is 262,144, but this dataset
measures approximately 8K inputs. Use the 256K protocol for long-context testing.
A separate 24K-input dataset also fits the current window.

`--warmup 4` sends four short warmup requests, not the measured 8K dataset.
`--cache-state` only labels a run; it does not flush or warm KV caches. This
starter sweep includes within-session reuse and cross-run reuse, so it uses the
honest `uncontrolled` label. Inspect repeat spread, especially the first run.
A controlled cold/warm comparison needs a separate cache-preparation procedure;
do not compare these runs with the previous cold-start smoke tests.

## 3. Read the notebook

Open `benchmarks/compare.ipynb` in your IDE and select `.venv/bin/python` as the
kernel. Set this in its first code cell **before the `RESULTS = ...` assignment**,
or set the equivalent environment variable before launching the notebook kernel:

```python
os.environ['DISAGG_RESULTS'] = str(ROOT / 'tracks/nvidia-dynamo/studies/deepseek-v4-pro-disagg-8k')
```

Run All. The notebook collects per-run summaries automatically; from the shell,
`python -m benchmarks.collect --results "$PERF_RESULTS"` does the same thing.

1. Check failures, invalid measurements and actual token lengths first.
2. Read the **Concurrency sweep** charts: aggregate output tokens/s, p95 TTFT,
   and p95 TPOT. Each point is the median of repeated runs at that concurrency;
   exported minimum/maximum throughput columns show repeat spread.
3. Use `COHORT_INDEX` for a detailed comparison at one concurrency level. Pick
   its row from the cohort table, then rerun that cell and the cells below it.
4. Read request-level latency distributions for the selected cohort.

PNG and CSV exports go under `$PERF_RESULTS/analysis/`, including
`concurrency-sweep.png` and `concurrency-sweep.csv`. SGLang does not expose the
explicit per-token IDs required by this runner for exact ITL; use TPOT and leave
ITL unavailable. TPOT is an average per request, not an individual-token tail.
The displayed p95s are medians of per-run p95s; they are not pooled p95s.

Choose the highest throughput that still meets your application's latency target.
192 requests per run are useful for initial curves, but do not support strong
p99 claims. Increase sessions and repetitions for tail-latency analysis.

## Client placement and GPU metrics

The public endpoint measures user-visible performance, including the client WAN,
LoadBalancer and stream buffering. For serving-stack capacity measurements, run
the same client from a CPU host/pod in the cluster's private network, using
`http://frontend.deepseek-v4-pro.svc.cluster.local:8000/v1` from a cluster pod.
Use a separate results folder for each client location. Copy the client code,
dataset and deployment record; do not download model weights onto the client.

From that private client, add both worker metric snapshots:

```bash
--metrics-url http://<NODE_A_IP>:8081/metrics \
--metrics-url http://<NODE_B_IP>:8081/metrics
```

Those private addresses are not reachable through the public LoadBalancer.
Metrics snapshots are saved alongside the run; the notebook does not currently
plot GPU utilization or separate prefill/transfer/decode timings. Do not use a
port-forward as the inference path for capacity tests.

To compare aggregated versus disaggregated later, run the same dataset, client
placement, GPU count, budgets and cache procedure against each actual topology,
with its matching deployment record. Do not relabel disaggregated results as
aggregated. The earlier validation CSVs are correctness evidence, not a fair
performance baseline.
