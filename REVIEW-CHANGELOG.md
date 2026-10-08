# Review changelog: lab/PoC to customer-facing blueprint

[Home](README.md) › Review changelog

Work done on branch `blueprint-production`, starting from `main` after its history was
rewritten to remove site identifiers. No cluster was used for any of this. **No benchmark
number was added**: every measured figure in the docs comes from the existing studies in
`tracks/nvidia-dynamo/studies/`, and everything else is labelled UNVALIDATED.

## Commits

| Commit | Phase | Change |
| --- | --- | --- |
| `922347b` | 0 | Scrub site identifiers from the tree; `render_site.py` + `site.env.example`; hygiene tests |
| (history) | 0 | `git filter-repo --replace-text` over all history; `main` force-pushed; merged branch deleted |
| `58e4986` | 1 | Raw evidence (629 files, 137 MB) moved into verified per-study release archives |
| `7d78082` | 1 | `deployments/` → `deploy/{sites,legacy-compose,prerequisites}`; every link rewritten |
| `29ec627` | 2 | Upstream verification record; vendored Dynamo CRD schemas; strict validator over `kustomize build` output |
| `d87cdca` | 1 | Own namespace per H200 profile; shared static PVs; lab variants over unchanged as-measured manifests |
| `804a746` | 1 | Unvalidated topologies moved to ROADMAP.md with proposed target dates; no VLM claim |
| `80438de` | 2 | `nvidia.com/v1beta1` DynamoGraphDeployments, flag-tested against the measured configuration |
| `2af93dd` | 2 | dynamo-platform 1.4.0 values: Kubernetes discovery, Grove + KAI, cert-manager webhook |
| `26a10e2` | 2, 4 | Production overlays: gateway/TLS/JWT/rate limits, NetworkPolicies, Planner, DGDR profiling |
| `1754e0b` | 3 | Every reliability finding → manifest mitigation + troubleshooting entry; driver lock |
| `8e32ecf` | 4 | GPU Operator v26.7.1 / Network Operator v26.7.0 values and NicClusterPolicy (RDMA device plugin) |
| `59ccdfb` | 4 | Observability: PodMonitors, alert rules, dashboard, canary; metric provenance inventory |
| `dd7eab8` | 5 | Open-loop load generator, goodput at SLO, cost, AIPerf export, sweeps, ISL/OSL distributions |
| `83a407c` | 7 | Ten prepared experiments with overlays, checklists and `tools/preflight.py` |
| `01375ec` | 6 | Ten PNG diagrams with editable draw.io sources; old SVGs removed |
| final commit on this branch | 6 | README, chapter 12, decision guide, glossary, engine-flag review, chapter summaries; this file |

## Phase 0: security scrub

- Replaced in tree and history:
  - the public LoadBalancer address
  - B300 public SSH addresses and the SSH user
  - node hostnames and node, pod and service IPs
  - PV names
  - the kube context
  - local home paths
- Values are now `<PLACEHOLDER>` tokens, filled by `tools/render_site.py` from a git-ignored
  `platform/site.env`. Drivers read node IPs from the environment.
- No tokens or keys were found in the tree or history. Commit author emails were left as
  standard Git metadata.
- `tests/test_site_hygiene.py` fails on any public or private IPv4 address, cloud node
  hostname, home path, literal kube context or token pattern.
- The replacement map lists the removed values, so it is kept outside the repository.

**Still required from the maintainer:**
1. Ask GitHub Support to purge `refs/pull/1/*`. It still points at the pre-rewrite
   commit `2ec2d26`, and a force-push cannot remove it.
2. Treat the old LoadBalancer address as exposed: firewall or rotate it.
3. Every other clone must re-clone; the old history is incompatible.
4. Delete the local backup `~/serving-solutions-pre-rewrite-20261001.bundle` and the map
   `~/scrub-replacements-serving-solutions.txt` once satisfied.
5. Set the local `origin` URL to `https://github.com/bhajian/model-serving-solutions.git`
   (`git filter-repo` removed it, and repointing it was blocked in this session).
6. Remove "VLM" from the GitHub repository description, which `gh` could not edit here.
7. Publish the result archives:
   `gh release create results-archive-2026-10-01 build/archives/*.tar.gz`.

## Verified offline

- `python -m pytest -q` passes: 210 tests.
- `python tools/validate.py` reports zero errors: 185 raw objects and 766 rendered
  kustomize objects across `deploy/` and `tracks/nvidia-dynamo/studies/planned/`.
  - It runs in strict mode: unknown fields are errors, because Kubernetes silently prunes
    them from custom resources.
  - Schemas: Kubernetes 1.33; Dynamo 1.4.0 DynamoGraphDeployment (v1beta1, v1alpha1) and
    DynamoGraphDeploymentRequest (v1beta1); Gateway API v1.3.0; Envoy Gateway v1.4.2;
    Prometheus Operator v0.83.0; cert-manager v1.17.2; Network Operator v26.7.0;
    Inference Extension v1.5.0.
- Every Dynamo, Planner, router and SGLang field is checked against the pinned sources
  (Dynamo `v1.4.0` / `0301494`, SGLang `v0.5.16`), with file and line, in
  [reference/upstream-verification.md](reference/upstream-verification.md).
- The operator graphs' engine flags equal the measured lab flags, except a documented set
  of mitigations (`tests/test_graphs.py`).
- Helm values: every key path exists in the vendored chart values (dynamo-platform,
  GPU Operator, Network Operator).
- Alert rules pass `promtool check rules`. Every metric in a rule or panel has a recorded
  provenance (`tracks/nvidia-dynamo/observability/metrics-inventory.txt`).
- Images: every image in `tracks/nvidia-dynamo/graphs`, the production overlays and the experiments is
  pinned by digest. Digests were read from the registries on 2026-10-01.
- The dataset generator's output without the new flags is byte-identical to the previous
  version.
- Every Markdown link resolves, and every embedded diagram exists.

## Decisions that differ from the brief, with the evidence

| Brief | What was done | Why |
| --- | --- | --- |
| 3-node etcd with TLS + auth in production | Kubernetes-API discovery, no etcd | Verified in 1.4.0: the operator's default `discoveryBackend` is `kubernetes`; etcd and NATS are optional. This removes the component behind the "channel closed" outage instead of hardening it |
| Planner with p99 TTFT/ITL inputs | p99 objectives translated into **mean** targets | The 1.4.0 Planner compares mean values from Prometheus histograms (`traffic_metrics.py` L208) |
| P:D ratio and replica counts as Planner outputs | One `max_gpu_budget` caps the graph | 1.4.0 has no `max_replicas` and no per-role budget |
| `freeze_gc` after warmup | `--gc-threshold 7000 10 100` plus an opt-in `sitecustomize` hook calling `gc.freeze()` | SGLang has `freeze_gc`, but Dynamo 1.4.0 never calls it and has no flag for it |
| Prometheus alert on the "prefill router deactivated" log pattern | Metric alert `DynamoPrefillWorkersMissing` on `dynamo_component_router_worker_registered` | Prometheus cannot alert on logs. Add a Loki rule for the log line if you run Loki |
| Readiness that checks prefill-router activation | Exec probe requiring discovered `prefill` instances in `/health` | No "prefill router active" metric exists in 1.4.0; `/health` returns 200 with zero workers |
| "Identical or better TPOT" for disaggregated | Stated per study: better in 8K/128K (14.15 vs 14.51 ms), worse in 128K (4.64 vs 4.35 ms) | That is what was measured |
| Native FP8 MoE path vs Marlin for DeepSeek | Marlin is compared with other MXFP4-capable backends | Upstream V4 Pro recipes use `flashinfer_mxfp4`, i.e. MXFP4 experts; Hopper lacks FP4 tensor cores |
| Every image pinned by digest | Done for base, production and experiments; lab `as-measured` manifests unchanged | The lab files are a record of what ran |

## TODO(verify-upstream)

| Item | Where |
| --- | --- |
| OCI chart paths for Grove (`oci://ghcr.io/ai-dynamo/grove/grove-charts`) and KAI (`oci://ghcr.io/kai-scheduler/kai-scheduler/kai-scheduler`); versions are verified from `platform-Chart.yaml` | `tracks/nvidia-dynamo/install/README.md` |
| The NGC chart URL from the 1.4.0 release notes returned HTTP 404 on 2026-10-01; fallback is building from the tag | `tracks/nvidia-dynamo/install/README.md` |
| Whether NicClusterPolicy `version` accepts a digest; the tag's digest is recorded | `platform/operators/nic-cluster-policy.yaml` |
| Which allocator causes the prefill host-memory swing (NIXL/UCX staging vs SGLang) | `reference/troubleshooting.md`, experiment 04 |
| DP attention and EP for DeepSeek V4 Pro on H200 (upstream recipes are TP8 only); Hopper support of non-Marlin MXFP4 MoE backends | experiment 05 |
| aiconfigurator support for this model on SGLang (needed for DGDR `rapid`; the profiling request uses `thorough`) | `tools/render_production.py` |
| `--router-decode-active-request-weight` is marked experimental upstream; the value (8000 ≈ one 8K prompt at page size 1) is a design choice to confirm | experiment 02 |
| The full Prometheus name `dynamo_component_router_worker_registered` is inferred from the `dynamo_component` prefix (the Planner's `dynamo_component_router_kv_hit_rate` follows it); confirm on the first scrape | experiment 00 |

## Tomorrow's run order

`python tools/preflight.py tracks/nvidia-dynamo/studies/planned/<nn> --context "$KUBE_CONTEXT"` before each. Durations
are planning estimates.

1. **00 site migration** (3–4 h): static PVs, operator, NVIDIA operators, observability,
   gateway, weights staging, first aggregated graph. Confirms the router metric name and
   RDMA without hostNetwork.
2. **01 P:D ratio sweep** (core rows ~4 h): the test that can show where disaggregation wins.
3. **02 KV router** (~1.6 h): confirms the 152/120 imbalance is fixed.
4. **04 reliability** (~3 h): GC, prefill memory cap and profile, discovery-loss restart,
   radix stall.
5. **03 Planner demo** (~4 h, profiling runs in the background).
6. **05 DeepSeek layout** (~4 h), **06 overlap scheduling** (~1 h), **07 chunk size** (~1.3 h).
7. **08 resilience and soak** (1.5 h + 24 h), **09 B300 validation** (one day, needs the B300 hosts).

After each experiment, commit its results, archive the raw evidence, and only then move its
rows from ROADMAP.md into the README's validated matrix.
