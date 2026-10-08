# 1 · Intake: the deployment profile

[Home](../../README.md) › [Framework](../README.md) › 1 · Intake

**Output:** one deployment profile per workload class, copied from
[profile.template.yaml](profile.template.yaml). **Gate:** every field is filled in or set to
`unknown` with a calibration step planned in stage 4. Mixed traffic gets one profile per
class (for example chat and coding); they are often best served by separate deployments
([blueprint 15 §6](../../blueprint/15-workload-driven-design.md#6-putting-it-together)).

## What to collect, and where it comes from

| Section | Fields | Source | Why it matters |
| --- | --- | --- | --- |
| `model` | Architecture, total and active parameters, weight size on disk, precision, context window, revision | Model card, `config.json`, checkpoint size | Minimum GPUs per worker, KV bytes per token, transfer intensity |
| `hardware` | GPU model and memory, GPUs per node, node count, scale-up domain, fabric, GPUDirect RDMA, storage type and throughput | Cluster inventory, `nvidia-smi topo -m`, storage class | Largest possible worker, whether P/D or wide EP can pay off, cold-load time |
| `workload` | Class, ISL and OSL distributions (p50, p99), prefix reuse, turns per session, think time, arrival pattern, peak concurrency | Gateway or application logs; otherwise the class defaults in [blueprint 15 §4](../../blueprint/15-workload-driven-design.md#4-workload-types) | The prefill-to-decode work ratio *R*, KV working set, routing value |
| `goal` | One primary goal: `long-context`, `output-optimized`, `sla`, `throughput-cost` | Agreed with the customer | Which metric and which study decide acceptance |
| `slo` | p99 TTFT, p99 ITL, minimum throughput, availability | Product requirement | Goodput definition for stage 4 |
| `constraints` | Platform (Kubernetes, OpenShift, Docker), required vendor support, allowed engines, data residency, budget | Customer | Narrows the track before any performance argument |

**Measuring reuse.** Prefix reuse *r* is the fraction of prompt tokens already seen by some
earlier request in the same session or across sessions (system prompts, shared documents,
agent history). Estimate it from logs by hashing prompt prefixes in fixed blocks. A high *r*
makes KV-aware routing and KV capacity the first lever, before P/D.

**Unknowns are allowed.** Write `unknown` and add the calibration to the validation plan
(for example, measure prefill tokens/s at the real ISL before sizing). Never fill a field from
a vendor datasheet when it can be measured.

## Examples

| Profile | Model | Hardware | Workload | Goal |
| --- | --- | --- | --- | --- |
| [deepseek-v4-pro-256k-multiturn.yaml](examples/deepseek-v4-pro-256k-multiturn.yaml) | DeepSeek V4 Pro 0813 (MoE + MLA, 893 GB) | 4 × 8 H200, InfiniBand | Three-turn sessions over 256K-token documents | Long context |

---

**Next:** [2 · Decide](../2-decide/README.md)
