# Planned studies

[Home](../../../../README.md) › [Tracks](../../../README.md) › [NVIDIA Dynamo](../../README.md) › [Studies](../README.md) › Planned

> **UNVALIDATED — scheduled.** Prepared offline for the next cluster session. Nothing here has been run.

Run in this order. Each folder has README.md (what and why), READY.md (checklist) and, where the layout changes, `configs/` overlays that pass the same strict validation as the track manifests.

| # | Experiment | Planning estimate |
| --- | --- | --- |
| 00 | [Move the H200 site to the operator path](00-site-migration/) | 3-4 h including weight staging |
| 01 | [P:D ratio and per-role TP on 16 H200 GPUs, goodput at SLO](01-pd-ratio-sweep/) | 6 configs x 6 RPS levels x 8 min + 6 layout changes x ~15 min = ~6.3 h; run the four rows marked core first (~4 h) |
| 02 | [KV router balance and prefix hit rate against round-robin](02-kv-router/) | 3 routers x (burst ~3 min + 3 RPS x 8 min) + 3 layout changes x ~5 min = ~1.6 h |
| 03 | [Planner adjusts the P:D layout against the SLO](03-planner-demo/) | profiling 2-4 h (operator-run Job) + 7 load steps x 10 min = ~4 h |
| 04 | [Confirm the reliability mitigations](04-reliability/) | (a) 3 x ~25 min, (b) shares (a), (c) ~20 min, (d) 2 x ~35 min: ~3 h |
| 05 | [DeepSeek V4 Pro: DP attention + EP, MTP, MoE backend, PD prefix reuse](05-deepseek-layout/) | 4 configs x (load ~40 min, warm start ~20 min) = ~4 h |
| 06 | [Overlap scheduling for hybrid Mamba (Nemotron 3 Nano)](06-overlap-scheduling/) | 2 configs x 3 RPS x 8 min + 2 layout changes = ~1 h |
| 07 | [Prefill chunk size at 128K context](07-prefill-chunk-size/) | 3 configs x ~25 min = ~1.3 h |
| 08 | [Failure injection and 24 h soak](08-resilience-soak/) | failure injection ~1.5 h; soak 24 h |
| 09 | [Validate the HGX B300 reference tracks end to end](09-b300-reference-validation/) | 4 tracks x ~2 h = ~8 h (one day) |

Check cluster readiness for any experiment with `python tools/preflight.py tracks/nvidia-dynamo/studies/planned/<nn-name> --context "$KUBE_CONTEXT"`.
