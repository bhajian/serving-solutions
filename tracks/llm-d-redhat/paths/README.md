# Well-lit paths

[Home](../../../README.md) › [Tracks](../../README.md) › [llm-d + Red Hat AI](../README.md) › Paths

One folder per path. Each `README.md` is the guide: what the path adds, when the framework
chooses it, prerequisites, how to deploy it with the RHAIIS image, how it is tested, and its
status here. Deployable manifests for one model on one site sit in a subfolder named
`<model>-<site>/` (for example `01-optimized-baseline/deepseek-v4-pro-h200/`).

| # | Path | Status |
| --- | --- | --- |
| 01 | [Optimized baseline](01-optimized-baseline/README.md) | Deployed; study running |
| 02 | [Precise prefix-cache routing](02-precise-prefix-cache-routing/README.md) | Planned |
| 03 | [Predicted-latency routing](03-predicted-latency-routing/README.md) | Planned |
| 04 | [Tiered prefix cache](04-tiered-prefix-cache/README.md) | Planned |
| 05 | [P/D disaggregation](05-pd-disaggregation/README.md) | Reference manifests |
| 06 | [Wide expert parallelism](06-wide-ep/README.md) | Planned |
| 07 | [Flow control](07-flow-control/README.md) | Planned |
| 08 | [Workload autoscaling](08-workload-autoscaling/README.md) | Planned |

**Guide template.** New path guides keep these sections: *What it adds* · *Choose it when* ·
*Prerequisites* · *Deploy* · *Test* · *Status*.
