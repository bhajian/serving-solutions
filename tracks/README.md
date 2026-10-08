# Solution tracks

[Home](../README.md) › Tracks

A track is one vendor solution stack carried from installation to measured studies. The
[framework](../framework/README.md) picks the track in decision D3 and the implementation in
D4; the tracks never decide, they implement and measure. Cluster prerequisites both tracks
share are in [platform/](../platform/README.md).

| | [Track 1 · NVIDIA Dynamo](nvidia-dynamo/README.md) | [Track 2 · llm-d + Red Hat AI](llm-d-redhat/README.md) |
| --- | --- | --- |
| Control plane | Dynamo 1.4.0 operator, frontend with KV router, Planner | llm-d router (endpoint picker + Envoy) on the Gateway API Inference Extension |
| Engines | SGLang, vLLM, TensorRT-LLM | vLLM from the Red Hat AI Inference Server image (SGLang upstream) |
| Unit of deployment | DynamoGraphDeployment per model; lab manifests as measured | One folder per well-lit path: guide, manifests, test |
| Measured here | Three studies on 2 × H200 (complete) | 256K routing study on 4 × H200 (running) |
| Support | NVIDIA AI Enterprise terms | Red Hat: OpenShift AI, selected managed Kubernetes; see the track |

## Folder conventions

Both tracks use the same top-level shape, so a reader can move between them:

| Folder | Track 1 | Track 2 |
| --- | --- | --- |
| `install/` | Dynamo operator values (Grove, KAI) | InferencePool CRDs, router chart, RHAIIS image and pull secret |
| Implementation | `graphs/`, `production/`, `sites/<site>/<model>/lab/` | `paths/<nn-path>/` (guide) and `paths/<nn-path>/<instance>/` (manifests for one model on one site) |
| `studies/` | Completed studies and `planned/` | Completed and running studies |
