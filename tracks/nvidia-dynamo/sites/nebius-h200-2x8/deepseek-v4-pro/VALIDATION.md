# Historical 32K disaggregated validation: 30 September 2026

This records the earlier 32K validation. The subsequent [256K comparison](../../../studies/deepseek-v4-pro-256k-comparison/REPORT.md) leaves the live deployment aggregated.

**DeepSeek V4 Pro served in prefill/decode disaggregated mode** at
`http://<LOADBALANCER_IP>:8000/v1`. Model ID: `deepseek-ai/DeepSeek-V4-Pro-0813`.
Namespace: `deepseek-v4-pro`; Kubernetes context: `$KUBE_CONTEXT`.

| Role | Deployment | Node | GPUs | Checkpoint PVC |
| --- | --- | --- | --- | --- |
| Prefill | `worker-0` | `<NODE_A_HOSTNAME>` | 8 H200, TP8 | `model-0` |
| Decode | `worker-1` | `<NODE_B_HOSTNAME>` | 8 H200, TP8 | `model-1` |

The pinned Dynamo 1.4.0 / SGLang 0.5.16 image and checkpoint revision are unchanged.
The workers use NIXL with its UCX backend for KV transfer. Context length remains
32,768; each role admits 16 requests. These are the historical settings; the current deployment files describe the subsequent 256K configuration.

## Inference and transfer verification

- Both workers, frontend and etcd are ready, with no worker restarts.
- Four concurrent arithmetic checks passed: two streaming and two non-streaming
  responses returned `42`; streams terminated with `[DONE]`.
- A tool request returned `multiply` with `{"a":19,"b":23}` and
  `finish_reason: tool_calls`.
- A 9,390-token retrieval prompt returned the exact code `NEBULA-48217` from the
  beginning of its input, with normal completion.
- The chatbot benchmark passed 12/12 requests at concurrency 4, with 8,000–8,074
  input tokens. Tool-history replay passed 6/6 at concurrency 2. All 18 server
  prompt counts matched the native DeepSeek encoder exactly.
- Matching request IDs completed on both the `prefill.generate` endpoint on node 0
  and the `backend.generate` endpoint on node 1. Logs show prefill batches on the
  first node and decode batches with KV transfer queues on the second.
- All eight ranks initialized `NIXL KVManager` with backend `UCX`. UCX logs select
  inter-node `rc_mlx5` transports. All eight InfiniBand port data counters increased
  during inference. TCP is excluded from `UCX_TLS`; control-plane TCP remains in
  use for discovery, bootstrap and Dynamo requests.
- Repository checks passed: 63 pytest tests, 75 structural schema validations,
  server-side dry-run of worker manifests, and `git diff --check`.

## Same weights, same storage, no download

| PVC | State | Capacity | Persistent volume |
| --- | --- | --- | --- |
| `model-0` | Bound | 1500Gi | `<PV_NAME>` |
| `model-1` | Bound | 1500Gi | `<PV_NAME>` |

The original completed download Jobs and PVCs were left unchanged. Workers loaded
`/model` offline from revision `72e1d3230f6c080a530b0a1d46f8eb4602340597`.
Before replacing the aggregated workers, their compiled caches were saved to
`.runtime` on the respective model PVCs. The new workers mount those caches
writable, while `/model` stays read-only. No additional storage was provisioned.

Cached checkpoint prefetch finished in at most 16.55 seconds. Prefill became
Kubernetes Ready 151 seconds after pod creation; decode became Ready after
165 seconds (22:09:24 UTC). This measured restart retained the nodes' OS page
cache and compiled caches. A cold node replacement can take substantially longer.

These remain separate RWO Nebius network SSD volumes, not a shared RWX filesystem.
Deleting the PVCs or namespace deletes the disks under the current `Delete`
reclaim policy. Both prefill and decode roles are required for serving.

## Benchmark records

| Workload | Local raw result directory | Tracked summary |
| --- | --- | --- |
| Chatbot, 12 requests | `tracks/nvidia-dynamo/studies/20260930T221002Z-e66927e3/` | [CSV](validation-disagg-chatbot-summary.csv) |
| Tool-history replay, 6 requests | `tracks/nvidia-dynamo/studies/20260930T221054Z-228e6cb7/` | [CSV](validation-disagg-agentic-summary.csv) |

The chatbot run took 13.50 seconds, with zero errors, 96,390 input tokens and
1,143 output tokens. Median TTFT was 1.44 seconds and mean per-request decode rate
was 66.51 tokens/second. These are small functional runs over the public endpoint,
with uncontrolled cache state and overlapping correctness checks. They are not
controlled capacity or aggregated-versus-disaggregated comparisons. Token-resolved
ITL is unavailable from this API stream; chunk intervals are not token ITL.
Tool-history replay does not execute tools or score task completion.

Local diagnostic evidence is in `build/deepseek-v4-pro-disagg/` (ignored): startup
and request logs, InfiniBand snapshots, saved caches, and correctness responses.
The [earlier aggregated validation](VALIDATION-AGGREGATED.md) remains available.
This validates this H200 site, not the separate B300/Nemotron or llm-d tracks.
