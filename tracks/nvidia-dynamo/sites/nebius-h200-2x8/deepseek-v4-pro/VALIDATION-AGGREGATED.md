# Historical aggregated validation: 30 September 2026

This records the earlier aggregated deployment, replaced by the
[disaggregated deployment](VALIDATION.md) later the same day. The endpoint was `http://<LOADBALANCER_IP>:8000/v1` in namespace
`deepseek-v4-pro`, context `$KUBE_CONTEXT`. Model ID:
`deepseek-ai/DeepSeek-V4-Pro-0813`. Both SGLang workers became ready at
21:44 UTC. Dynamo 1.4.0 routes to two aggregated TP8 replicas on 16 H200 GPUs;
SGLang was 0.5.16. This report and its CSV summaries describe the earlier
aggregated configuration, not the current deployment.json.

## Verified

- Both worker Deployments, frontend and etcd are available. Both download Jobs
  completed. Worker logs confirm generation requests completed on both nodes.
- Public LoadBalancer discovery returns the model with a 32,768-token context.
- Four concurrent arithmetic requests (two streaming, two non-streaming) returned
  `42`, including normal completion and SSE `[DONE]` termination.
- The README Kubernetes explanation prompt returned three sentences with
  `finish_reason: stop`; 24 prompt tokens, 85 completion tokens, 2.43 seconds
  observed end-to-end latency for that individual request.
- A tool request returned `multiply` with JSON arguments `{"a":19,"b":23}` and
  `finish_reason: tool_calls`.
- The repository chatbot benchmark completed 12/12 requests successfully at
  concurrency 4, with 8,000–8,074 prompt tokens and up to 128 output tokens.
  All 12 server prompt counts exactly matched the local DeepSeek encoder.
- The agentic tool-history replay completed 6/6 requests at concurrency 2. All
  server prompt token counts matched the native encoder, including tool schemas,
  assistant tool calls and tool results. This replays recorded histories; it does
  not execute tools or score task completion.
- Offline checks: 63 pytest tests passed; 75 manifest objects passed upstream
  structural schema validation; server-side dry-run accepted the site manifests.

## Benchmark evidence

The local raw results are in
`tracks/nvidia-dynamo/studies/20260930T214515Z-bf7cabd1/` (ignored generated files).
The tracked `validation-chatbot-summary.csv` preserves the aggregate result.
Tool-history replay results are in `tracks/nvidia-dynamo/studies/20260930T214644Z-2ce4733f/`, with
aggregate results in `validation-agentic-summary.csv`.
The run took 32.88 seconds for 12 requests, with zero errors, 96,390 input tokens
and 1,053 output tokens. Median TTFT was 6.90 seconds; mean per-request decode
rate was 73.08 tokens/second.

This was a functional test after startup, including initial prefill compilation,
an uncontrolled prefix cache and overlapping smoke requests. Timings include the
external client's WAN and LoadBalancer latency. These numbers do not establish
steady-state throughput, maximum capacity, or comparative performance. The API
stream did not expose token-resolved ITL; chunk intervals are not token ITL.

## Storage and recovery

| PVC | State | Capacity | Persistent volume |
| --- | --- | --- | --- |
| `model-0` | Bound | 1500Gi | `<PV_NAME>` |
| `model-1` | Bound | 1500Gi | `<PV_NAME>` |

Both use Nebius CSI network SSD storage, `compute-csi-default-sc`, RWO access.
Workers mount the checkpoint read-only and run offline, using the pinned revision
marker. Replacing a pod preserves the model volume and avoids another download.
These are separate per-node model copies. Shared filesystem work was deferred.
Compiled kernel caches are currently ephemeral; pod restart recovery time was
not measured. Deleting the PVCs or namespace deletes the underlying disks under
the current `Delete` reclaim policy.

## Corrections made during deployment

The new H200 site manifests supply appropriate model, kernel, memory, placement,
networking and persistent checkpoint settings. Explicit checkpoint prefetch fixed
cold network-filesystem GPU copy stalls. Downloads took about 32 minutes; cold
prefetch took about 23 minutes and subsequent kernel initialization about
12 minutes before readiness.

The dataset generator now supports the checkpoint's native DeepSeek V4 Python
encoder because this model does not ship a Hugging Face Jinja chat template.
The adapter preserves tool argument strings and avoids adding another BOS token.
Regression tests cover the adapter and explicit trust requirement. The directory
check also ignores generated datasets so running the documented workflow does
not break repository tests.

This validates the new H200 deployment only. It does not validate the separate
B300/Nemotron, disaggregated or llm-d deployment tracks.
