# Upstream verification (pinned sources)

[Home](../README.md) › [Reference](README.md) › Upstream verification

Every CRD field, flag and environment variable used by the operator path in
[tracks/nvidia-dynamo/graphs](../tracks/nvidia-dynamo/graphs/) and [tracks/nvidia-dynamo/LAB-VS-PRODUCTION.md](../tracks/nvidia-dynamo/LAB-VS-PRODUCTION.md) was checked
against these pinned source trees. Paths are relative to each checkout.

| Source | Tag | Commit |
| --- | --- | --- |
| [ai-dynamo/dynamo](https://github.com/ai-dynamo/dynamo/tree/v1.4.0) | `v1.4.0` | `03014943323e78feb5bd672ef08b72caea0918ac` (2026-08-14) |
| [sgl-project/sglang](https://github.com/sgl-project/sglang/tree/v0.5.16) | `v0.5.16` | shallow clone of the tag |

CRD schemas for `kubeconform` are converted from the Dynamo CRDs under
`tracks/nvidia-dynamo/install/config/crd/bases/` and vendored in [upstream/](upstream/).

## DynamoGraphDeployment (`nvidia.com`)

- `v1beta1` is served and converts through the operator webhook; `v1alpha1` is
  deprecated but is still the storage version
  (`nvidia.com_dynamographdeployments.yaml` L35-37, L12131, L12147, L21498-21512).
  **This repository writes `v1beta1`.**
- v1beta1 spec: `components[]` with `name`, `type`
  (`frontend|worker|prefill|decode|planner|epp`, L20919), `replicas`,
  `multinode.nodeCount` (≥ 2), `minAvailable` (Grove only), `sharedMemorySize`,
  `scalingAdapter`, `topologyConstraint`, `compilationCache`, and `podTemplate` (a
  native PodTemplateSpec whose container must be named `main`, L12201-12210, L12731).
  Top level: `backendFramework` (`sglang|vllm|trtllm`), `env`, `annotations`,
  `labels`, `priorityClassName` (Grove pathway), `restart`, `topologyConstraint`.
- RDMA: upstream requests `rdma/ib` through resource limits
  (`recipes/deepseek-v4/deepseek-v4-pro/sglang/disagg-b200/deploy.yaml` L81-90).
- Operator-injected defaults: frontend port 8000, liveness `/live`, readiness `/health`
  (`tracks/nvidia-dynamo/install/internal/dynamo/component_frontend.go` L42-80). Workers expose the
  `system` port 9090 with `/live` and `/health`, and a startup probe of 720 × 10 s
  (`component_worker.go` L28-109). Worker readiness does not gate traffic; routing
  uses discovery (L55-57).

## Discovery, etcd and NATS

- The operator's default discovery backend is **Kubernetes** (`values.yaml` L103;
  `api/config/v1alpha1/types.go` L436-451). It injects `DYN_DISCOVERY_BACKEND=kubernetes`
  (`component_common.go` L138-144). A DGD may override this with the annotation
  `nvidia.com/dynamo-discovery-backend`.
- etcd and NATS are not installed by default (`global.etcd.install: false`,
  `global.nats.install: false`). NATS is optional because the request and event planes
  default to TCP and ZMQ (`runtime_args.py` L150-166; `lib/runtime/src/distributed.rs`
  L725-738).
- **Consequence:** the production overlay uses Kubernetes discovery and deploys no
  etcd. The lab overlay keeps the single etcd it was measured with.

## Grove and gang scheduling

- `dynamo-platform` 1.4.0 pins Grove `v0.1.0-alpha.12-rc1` and KAI scheduler `v0.13.4`
  (`deploy/helm/charts/platform/Chart.yaml` L39-47).
- The chart always renders an explicit `grove.enabled` (`enabled OR install`), which
  disables auto-detection. Set `global.grove.enabled=true`
  (`components/operator/templates/operator-config.yaml` L57-66; `internal/features/gates.go`
  L248-259).
- With the gate on, every DGD is reconciled as a Grove PodCliqueSet unless annotated
  `nvidia.com/enable-grove: "false"` (`dynamographdeployment_controller.go` L441-473).
  Multinode components without Grove or LWS fail (L430-435). The PodCliqueSet name
  plus component name must be at most 45 characters (`consts.go` L218).

## Frontend routing and health

Flags are in `components/src/dynamo/common/configuration/groups/router_args.py` (R)
and `kv_router_args.py` (K).

| Flag | Default | Env |
| --- | --- | --- |
| `--router-mode` (R:158) | `round-robin` | `DYN_ROUTER_MODE` |
| `--router-min-initial-workers` (R:181) | `0` | `DYN_ROUTER_MIN_INITIAL_WORKERS` |
| `--router-decode-active-request-weight` (K:224, experimental) | `0.0` | `DYN_ROUTER_DECODE_ACTIVE_REQUEST_WEIGHT` |
| `--router-kv-overlap-score-credit` (K:176) | `1.0` | `DYN_ROUTER_KV_OVERLAP_SCORE_CREDIT` |
| `--router-prefill-load-scale` (K:212) | `1.0` | `DYN_ROUTER_PREFILL_LOAD_SCALE` |
| `--router-temperature` (K:265) | `0.0` | `DYN_ROUTER_TEMPERATURE` |
| `--router-replica-sync` (K:289) | `false` | `DYN_ROUTER_REPLICA_SYNC` |
| `--router-queue-threshold` | none | |
| `--active-decode-blocks-threshold` (R:222) | none | `DYN_ACTIVE_DECODE_BLOCKS_THRESHOLD` |
| `--active-prefill-tokens-threshold-frac` (R:248) | none | `DYN_ACTIVE_PREFILL_TOKENS_THRESHOLD_FRAC` |

- **KV router cost** (`lib/kv-router/src/scheduling/selector.rs` L138-308):
  `prefill_load_scale × max(0, prefill_blocks − overlap_credit) + decode_blocks +
  decode_active_request_weight × active_requests`. Lowest wins; ties break at random.
  With unique prompts and the default weight of 0, the router balances on tokens and
  blocks, not request count. Prefill tokens leave a worker's load once its prefill
  completes (`local.rs` L472). During a burst, workers that finish prefill sooner
  attract more requests. This explains the 152/120/120/120 split recorded in the
  8K/128K study.
- **Frontend `/health` returns 200 with zero registered workers, and also after the
  prefill router deactivates** (`lib/llm/src/http/service/health.rs` L63-98;
  `discovery/model_manager.rs` L1430-1460). It is not a model-servable signal. The
  router exports `router_worker_registered{worker_type}` per worker
  (`lib/llm/src/kv_router/metrics.rs` L398-404); there is no "prefill router active"
  gauge.

## Planner and profiling

- Deployed as a DGD component of type `planner` with image
  `nvcr.io/nvidia/ai-dynamo/dynamo-planner:1.4.0`. It is configured with
  `--config <json|path>` (`components/src/dynamo/planner/__main__.py` L60-67). Unknown
  config keys are ignored (`config/planner_config.py` L344).
- SLA scaling requires `optimization_target: sla`; otherwise `ttft_ms`/`itl_ms` are
  ignored (L797-813). Defaults: `ttft_ms` 500, `itl_ms` 50,
  `throughput_adjustment_interval_seconds` 180, `max_gpu_budget` 8, `min_endpoint` 1.
  There is **no `max_replicas` and no per-role GPU budget**; one `max_gpu_budget` caps
  the graph.
- It reads `dynamo_frontend_time_to_first_token_seconds`,
  `dynamo_frontend_inter_token_latency_seconds`,
  `dynamo_frontend_requests_started_total` and the ISL/OSL histograms from Prometheus
  (`PROMETHEUS_ENDPOINT`). These are filtered by `model` and by a `dynamo_namespace`
  label that the frontend does not emit; the operator's PodMonitor adds it from the
  pod label `nvidia.com/dynamo-namespace` (`templates/prometheus.yaml` L43-54).
  Scrape configs here add the same relabel.
- Profiling uses a `DynamoGraphDeploymentRequest` (`nvidia.com/v1beta1`, storage
  version). It takes `model`, `backend`, `sla.{ttft,itl}`, `workload.{isl,osl,requestRate}`,
  `hardware.{totalGpus,numGpusPerNode,gpuSku}`, `searchStrategy` (`rapid|thorough`),
  `autoApply` and `features.planner`. The operator generates the profiling Job itself
  (`dynamographdeploymentrequest_controller.go` L1519-1650); upstream ships no
  standalone Job manifest.

## SGLang v0.5.16 engine flags (`python/sglang/srt/server_args.py`, S)

- `--disable-overlap-schedule` exists (S:848); there is no `--enable-overlap-schedule`.
  For hybrid Mamba models such as Nemotron-H, with the radix cache on, `no_buffer`
  forces overlap off. `extra_buffer` allows overlap when `linear_attn_backend` is
  `triton` (`arg_groups/overrides.py` L1111-1201; S:4822-4829).
- `--mamba-radix-cache-strategy` `auto|no_buffer|extra_buffer|extra_buffer_lazy`
  (S:2121); `--disable-radix-cache` (S:827); `--radix-eviction-policy`
  `lru|lfu|slru|priority` (S:811).
- `--max-running-requests` (S:694), `--max-prefill-tokens` (16384, S:722),
  `--prefill-max-requests` (S:733), `--chunked-prefill-size` (S:714). `--max-queued-requests`
  (S:697) is ignored with disaggregation.
- GC: `--gc-threshold` (1–3 ints, S:1046), `--gc-warning-threshold-secs` (S:1336).
  `freeze_gc` exists as `POST /freeze_gc` (`entrypoints/http_server.py` L1125) and
  `Engine.freeze_gc()` (`entrypoints/engine.py` L1223). **Dynamo 1.4.0 never calls it and
  has no flag for it.**
- Disaggregation: `--disaggregation-decode-extra-slots`, `--num-reserved-decode-tokens`
  (512); there are no `--disaggregation-prefill-*` flags. Transfer queue depth is the
  env var `SGLANG_DISAGGREGATION_QUEUE_SIZE` (default 4; `environ.py` L372-412).
- MoE and parallelism: `--moe-runner-backend` includes `marlin` and `cutlass` (S:251-267,
  S:1954); `--enable-dp-attention` (S:977); `--ep-size` (S:1928); `--moe-a2a-backend`
  includes `deepep` and `nixl` (S:1936). `--speculative-algorithm` accepts
  `EAGLE|EAGLE3|NEXTN|...`; `NEXTN` is the MTP path for DeepSeek, and there is no literal
  `MTP` value (`speculative/spec_info.py` L35-42).
- Dynamo passes every SGLang `ServerArgs` through (`components/src/dynamo/sglang/args.py`
  L330-377, L558) and serves `clear_kv_blocks`, which refuses while requests are active
  (`request_handlers/handler_base.py` L826-870).
