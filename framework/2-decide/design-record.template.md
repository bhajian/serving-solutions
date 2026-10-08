# Design record: <profile name>

[Home](../../README.md) › [Framework](../README.md) › [2 · Decide](README.md) › Design record template

Copy this file next to the deployment profile. One record per profile.

| Field | Value |
| --- | --- |
| Profile | <link to the filled profile.yaml> |
| Date, authors | |
| Status | draft / agreed / validated / superseded |

## Decisions

| # | Decision | Choice | Because (matrix row, constraint or study) | Confidence |
| --- | --- | --- | --- | --- |
| D1 | Serving pattern | e.g. aggregated + prefix-aware routing | e.g. workload row "multi-turn chat"; P/D precondition 3 fails (fleet of 4) | measured / predicted |
| D2 | Model layout | e.g. TP8 per node, FP8 KV, no speculation | e.g. weights 893 GB need 8 × H200 | |
| D3 | Track | e.g. llm-d + Red Hat AI | e.g. customer requires Red Hat support | |
| D4 | Path | e.g. llm-d path 01, optimized baseline | pattern map row | |

## Optimization goal and acceptance

| Goal | Metric | Target | Study that proves it |
| --- | --- | --- | --- |
| | | | |

## Risks and open questions

| Risk or unknown | Impact | Resolved by (calibration or study) |
| --- | --- | --- |
| | | |

## Validation plan

1. Functional smoke: <command or study>
2. Calibration: <for each `unknown` in the profile>
3. Acceptance at SLO: <study and criteria>
