# Troubleshooting

[Home](../README.md) › [Reference](README.md) › Troubleshooting

Most problems fall into one of three layers. Diagnose them in this order, because each layer depends on the one before it.

1. **Control path** over Ethernet: etcd, HTTP and the TCP request plane.
2. **Worker startup:** image, model files and GPU memory.
3. **Data path** over InfiniBand: RDMA KV transfer through NIXL and UCX.

A working etcd connection does **not** prove RDMA works, and a failed etcd connection says nothing about InfiniBand. Keep the checks separate.

## Symptoms and actions

| Symptom | Likely cause | Action |
|---|---|---|
| etcd: `cannot assign requested address` | Listener bound to a specific IP | Keep `--listen-client-urls=http://0.0.0.0:2379`. The advertised URL stays the Node A IP (Docker) or the Service name (Kubernetes). |
| etcd healthy on Node A, unreachable from Node B | Routing or firewall | `ip route get <node-a-ip>` and `curl -v http://<node-a-ip>:2379/health` from Node B. Open 2379 between the private IPs only. |
| Frontend: `Interface not found: 10.x.x.x`, or `TcpListener on fe80::…` / `Invalid argument (os error 22)` | `DYN_TCP_RESPONSE_STREAM_HOST` was set | Remove it. Dynamo 1.4.0 auto-detects IPv4 correctly. No reference file sets it, and a test enforces that. |
| Model missing from `/v1/models` | Workers not registered, or a discovery mismatch | Wait for worker readiness, then read the frontend logs. Check that `DYN_NAMESPACE` and `ETCD_ENDPOINTS` are identical on all components. |
| Worker exits: `Checkpoint revision mismatch` | Different or missing `DEPLOYED_REVISION` | Re-run `tools/download_model.py` on the node. Both nodes must print the same SHA. |
| Worker OOM at startup | Context or concurrency too high for the memory share | Lower `--max-model-len` / `--max-num-seqs`, or keep `--gpu-memory-utilization` at 0.80 until stable |
| GPU busy, or container `already in use` | A previous track or manual container still running | `nvidia-smi`, `docker ps -a`, `kubectl get pods -A -o wide`. Stop it with its own `down` or `delete` command. |
| Request stalls after prefill (disaggregated) | KV transfer cannot connect | Check `UCX_NET_DEVICES` / `IB_DEVICES`, `/dev/infiniband` in the container, `IPC_LOCK` and memlock, side-channel port 5600 (vLLM) or bootstrap port 8998 (SGLang) reachable from Node B, and NIXL/UCX log lines naming the right devices |
| Transfers work but are slow | Staging through host memory, or the wrong interface | Confirm GPUDirect RDMA (`nvidia_peermem` or DMA-BUF). Confirm UCX is using `rc_x`/`rc` on `mlx5_*`, not TCP. Watch the IB port counters. |
| Mamba, cache or backend errors | Mixed engine versions or mismatched roles | Keep the pinned image. Make sure prefill and decode have identical model, TP, block size and KV dtype. Capture the **first** error. |
| Kubernetes pod `Pending` | Missing node label, GPUs taken, or taints | `kubectl describe pod`. Check `kubectl get nodes -L llm-serving/node`. |
| Kubernetes worker advertises the wrong IP | Node InternalIP is not the private IP | `kubectl get nodes -o wide`. Fix the kubelet `--node-ip`. |
| Disk usage climbs | Model copies, images, caches | `docker system df`, `du -sh /data/*/runtime/*`. Logs in the reference files are size-limited. |

## Failures observed on the H200 site and their fixes

Each entry below happened during a recorded study. The evidence is in `tracks/nvidia-dynamo/studies/` and
the release archives. The fix lives in the production manifests and is scheduled for
confirmation in [tracks/nvidia-dynamo/studies/planned/04-reliability](../tracks/nvidia-dynamo/studies/planned/04-reliability/).

### KV router imbalance: 152 / 120 / 120 / 120 requests per worker

**Seen in:** 8K/128K study, third aggregated run (excluded; kept under
`tracks/nvidia-dynamo/studies/nemotron-3-nano-8k-128k-comparison/excluded-runs/router-imbalance`). One
worker received 152 of 512 simultaneous requests. With a cap of 136 per worker, 16
requests queued for 37 minutes and the run reported 21,968 tokens/s instead of
about 34,700.

**Cause** (Dynamo 1.4.0, `lib/kv-router/src/scheduling/selector.rs` L138-308): the
KV router's cost is `prefill_load_scale × max(0, prefill_blocks − overlap) +
decode_blocks + decode_active_request_weight × active_requests`, lowest wins. With
unique prompts the overlap is 0. With the default `decode_active_request_weight` of 0,
requests are balanced by tokens, not count. A worker's prefill tokens leave its load
once its prefill completes (`local.rs` L472), so during a burst the workers that finish
prefill sooner look lighter and attract more requests. Starting to route before every
worker registers makes this worse (`--router-min-initial-workers` defaults to 0).

**Fix:** the operator graphs set `--router-decode-active-request-weight` (one prompt's
worth of blocks per active request; experimental in 1.4.0),
`--router-min-initial-workers` equal to the number of routable workers, and
`--router-replica-sync` for two frontends. The lab fell back to `round-robin`;
`tests/test_production.py` fails if any base or production manifest uses round-robin.
Confirm with [tracks/nvidia-dynamo/studies/planned/02-kv-router](../tracks/nvidia-dynamo/studies/planned/02-kv-router/).

### Endpoint returns 503 "not ready" while every pod is Ready

**Seen in:** after the 8K/128K study. The frontend logged `KeyValueStoreManager.watch
failed ... channel closed` and removed all workers. A frontend restart re-registered
the decode workers, but the prefill worker's etcd registration was gone ("Prefill router
deactivated"); restarting the prefill worker restored service.

**Cause:** the frontend's `/health` returns 200 even with zero registered workers and
after the prefill router deactivates (`lib/llm/src/http/service/health.rs` L63-98), so
Kubernetes saw nothing wrong. The lab used a single etcd and lease-based registration.

**Fix:** production uses Kubernetes-API discovery (the operator default; no etcd).
The frontend runs `tracks/nvidia-dynamo/common/frontend_probe.py`. Its readiness fails unless
`/health` lists a `generate` instance for every required component (`backend`, plus
`prefill` in PD mode). Its liveness fails once workers that were seen stay missing for
more than 5 minutes, so the frontend restarts and re-watches discovery. The alert
`DynamoPrefillWorkersMissing` fires when `router_worker_registered` shows decode
workers but no prefill workers. In the lab, restart the frontend first, then any worker
missing from `/health`.

### Prefill pod host memory swings 104 → 308 GiB and is OOM-killed at 384 GiB

**Seen in:** 8K/128K diagnostics. The prefill worker was OOM-killed 2 minutes 43
seconds after the last measured run, while a 6-request warmup was running. A
384-request burst then swung its anonymous memory between 104 and 308 GiB, settling
at 201 GiB during decode. Flushing the KV cache did not release it. Decode workers
stayed at 11–13 GiB.

**Mitigation:** the prefill role has its own host-memory limit (448Gi, against the
308 GiB peak), and `--max-running-requests 32` on prefill bounds how many requests hold
staging memory at once. The alert `DynamoPrefillHostMemoryHigh` fires at 70% of the
limit. The allocator responsible (NIXL/UCX staging vs SGLang) is not identified:
`TODO(verify-upstream)`, profiled in experiment 04.

### Token output pauses ~0.4 s every ~11 s on every stream of a worker

**Seen in:** both topologies of the 8K/128K study, about 190 pauses per request, which
set ITL p99.9 to about 500 ms. With `--gc-warning-threshold-secs 0.1`, SGLang logged 26
generation-2 collections in about 300 s, each 0.34–0.45 s and scanning about 890K objects.
GPU decode steps continued; the pause was on the output path.

**Mitigation:** `--gc-threshold 7000 10 100` (applied by SGLang in the engine's main
process, `entrypoints/engine.py` L793, L1351-1355) makes generation-2 collections about
100× rarer. Setting `SERVING_GC_FREEZE_AFTER_S` enables a `sitecustomize` hook that runs
`gc.collect(); gc.freeze()` once after warmup, as SGLang recommends; Dynamo 1.4.0 does
not call SGLang's `freeze_gc` itself. Before/after ITL p99.9 is scheduled in experiment 04.

### Every stream on a worker freezes ~37 s just before completing

**Seen in:** all aggregated 8K/128K runs. When 128 sequences of about 139K tokens finish
within a few seconds, every stream on that worker stops for about 37 s (the 40 s worst
ITL). It never occurred on disaggregated decode workers, which run without a radix cache
in SGLang PD mode. That points to the radix-tree insertion of finished sequences; it is
not proven.

**Mitigation:** for workloads without prefix reuse, add the Kustomize Component
[`tracks/nvidia-dynamo/production/components/no-prefix-reuse`](../tracks/nvidia-dynamo/production/components/no-prefix-reuse/)
to an aggregated overlay. It adds `--disable-radix-cache`. Keep the radix cache for
chat and agent traffic, where prefix reuse is the main TTFT lever. Confirmation run:
experiment 04.

### A second benchmark driver overwrote a cache-flush log

**Seen in:** 8K/128K aggregated run 1. The workers refused the second driver's flush
because requests were active, so the measurement was safe, but its log replaced the
first driver's. **Fix:** `benchmarks/driver_lock.py` gives every driver an exclusive lock
per results directory, and `clear_cache.py` appends timestamped acknowledgements to
`study-records/cache-flush-evidence.jsonl`. `tests/test_driver_lock.py` covers both.

### First disaggregated requests after a restart take about 60 s

NIXL connection setup between a new prefill/decode pair happens on the first
transferred request. Send a short warmup before measuring; every benchmark driver does.

## DeepSeek V4 / SGLang stalls after shard loading on network storage

The shard progress bar can reach 100% before GPU copies finish. On the H200
Nebius deployment, native stacks showed concurrent copies blocked in
`cuMemcpyHtoDAsync` / `pthread_rwlock_wrlock`. For checkpoints that fit in host
RAM, enable `--weight-loader-prefetch-checkpoints` and allow time for the cold
disk read; see [SGLang #29268](https://github.com/sgl-project/sglang/issues/29268)
and the [site manifests](../tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/). Watch disk-read
and page-cache progress as well as GPU utilization. Do not interpret shard
completion or frontend health as model readiness.

## Useful commands

```bash
# Docker: state and logs (run on the node, from the repository root)
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/<track>/node-a.yaml ps -a
docker compose --env-file tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/cluster.env -f tracks/nvidia-dynamo/sites/hgx-b300-2x8/compose/<track>/node-a.yaml logs --tail 200 <service>

# Kubernetes
kubectl -n <namespace> get pods -o wide
kubectl -n <namespace> describe pod <pod>
kubectl -n <namespace> logs deployment/<name> --tail 200

# Worker health and metrics
curl -fsS http://<node-ip>:8081/health
curl -s  http://<node-ip>:8081/metrics | grep -Ei 'nixl|transfer|kv'

# InfiniBand
ibv_devinfo -l
cat /sys/class/infiniband/mlx5_4/ports/1/counters/port_xmit_data
```

For the original step-by-step manual deployment, including frontend recovery, see [manual-docker-walkthrough.md](../tracks/nvidia-dynamo/sites/hgx-b300-2x8/manual-docker-walkthrough.md#10-diagnose-a-failed-check).
