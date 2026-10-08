"""Diagram specs: plain data on a pixel grid (rendered at 2x by tools/render_diagrams.py).

Element types:
  groups  {x, y, w, h, label, style?, badge?}           labelled container
  boxes   {x, y, w, h, label, sub?, style?, size?, align?}  styles: plain soft shade accent solid ghost dark;
                                                        align='top' pins text to the top of a region box
  arrows  {points: [(x, y), ...], label?, label_at?, style?: accent|muted, dashed?, both?}
  texts   {x, y, text, size?, color?, weight?, ha?}
  points  {x, y, label, style?}
"""

DIAGRAMS = {}

# ----------------------------------------------------------------------------- 1. serving stack
# Status of each part: 'v' validated on H200 (recorded studies), 'r' manifests or reference, not yet run,
# 'p' roadmap (ROADMAP.md), '' generic. Draws as accent, plain, ghost and soft boxes.
_STYLE = {'v': 'accent', 'r': 'plain', 'p': 'ghost', '': 'soft'}
_X0, _X1, _GAP = 300, 1560, 14


def _row(y, h, items, x0=_X0 + 20, x1=_X1 - 20, size=12):
    """Equal-width boxes across [x0, x1]; items are (label, sub, status)."""
    w = (x1 - x0 - _GAP * (len(items) - 1)) / len(items)
    return [{'x': x0 + i * (w + _GAP), 'y': y, 'w': w, 'h': h, 'label': label, 'style': _STYLE[st], 'size': size,
             **({'sub': sub} if sub else {}), **({} if st == 'v' else {'weight': 'normal'} if not sub else {})}
            for i, (label, sub, st) in enumerate(items)]


def _layer(y, h, label, decides):
    return ({'x': _X0, 'y': y, 'w': _X1 - _X0, 'h': h, 'label': label.upper(), 'style': 'soft'},
            {'x': 40, 'y': y + 14, 'text': decides, 'size': 11.5, 'color': 'muted', 'style': 'italic'})


_LAYERS = [  # (y, height, label, what the layer decides)
    (100, 110, 'Applications', 'what the workload looks like:\nprompt and output lengths, reuse'),
    (226, 110, 'Access layer', 'who may call, how much,\nover which API'),
    (352, 290, 'Serving control plane', 'where each request runs,\nhow many workers of each role'),
    (658, 160, 'Inference engines', 'how a batch runs on a GPU'),
    (834, 130, 'Model architectures', 'KV size per token\nand the parallelism that fits'),
    (980, 130, 'Data movement and memory', 'how KV and activations\nmove between GPUs and tiers'),
    (1126, 250, 'Hardware', 'memory, bandwidth and\nthe size of the NVLink domain'),
]
_groups, _texts = zip(*(_layer(*l) for l in _LAYERS))
_PLANES = [
    {'x': _X0 + 20, 'y': 390, 'w': 600, 'h': 236, 'label': 'NVIDIA Dynamo  ·  engine-agnostic, Docker or Kubernetes',
     'style': 'ghost', 'badge': 'RUN ON H200', 'badge_color': 'accent_ink'},
    {'x': _X0 + 640, 'y': 390, 'w': 600, 'h': 236, 'label': 'llm-d  ·  Kubernetes-native, Gateway API',
     'style': 'ghost', 'badge': 'REFERENCE · NOT YET RUN'},
]

DIAGRAMS['serving-stack'] = {
    'size': (1600, 1460), 'title': 'The LLM serving stack',
    'subtitle': 'A supercomputer for inference: every layer is a choice, and the choices must fit together. '
                'The engine must support the model; the control plane must support the engine.',
    'groups': [*_groups, *_PLANES],
    'boxes': [
        *_row(140, 54, [('Chat assistants', '', ''), ('Agents and tools', '', ''), ('RAG and search', '', ''), ('Batch and offline', '', '')]),
        *_row(266, 54, [('OpenAI-compatible API', '', 'v'), ('Gateway API · Envoy', '', 'r'), ('AuthN/Z · quotas', '', 'r'), ('TLS · rate limits', '', 'r')]),
        *_row(430, 88, [('Frontend + KV router', 'OpenAI API\nprefix-aware', 'v'), ('Planner', 'SLA scaling of P and D', 'r'),
                        ('Operator · Grove', 'graph CRD\ngang scheduling', 'r')], x0=_X0 + 36, x1=_X0 + 604, size=11.5),
        *_row(526, 88, [('NIXL transfer', 'KV between workers', 'v'), ('Discovery', 'Kubernetes API or etcd', 'v'),
                        ('KV block manager', 'G1–G4 tiers', 'p')], x0=_X0 + 36, x1=_X0 + 604, size=11.5),
        *_row(430, 88, [('Envoy gateway', 'Inference Extension', 'r'), ('Endpoint picker', 'prefix · load\nP/D scorers', 'r'),
                        ('P/D routing sidecar', 'on the decode pod', 'r')], x0=_X0 + 656, x1=_X0 + 1224, size=11.5),
        *_row(526, 88, [('InferencePool', 'selects model servers', 'r'), ('KV-cache indexer', 'cluster prefix index', 'r'),
                        ('Variant autoscaler', 'per-role scaling', 'r')], x0=_X0 + 656, x1=_X0 + 1224, size=11.5),
        *_row(696, 72, [('TensorRT-LLM', 'NVIDIA-optimized kernels · NVFP4', 'p'), ('vLLM', 'broad model and hardware support', 'r'),
                        ('SGLang', 'RadixAttention · agentic workloads', 'v')], size=13),
        *_row(872, 88, [('Dense', 'GQA attention', ''), ('MoE', 'sparse experts\nDeepSeek V4', 'v'), ('MLA', 'latent KV', ''),
                        ('Hybrid', 'Mamba + attention\nNemotron 3', 'v'), ('Sliding window', 'bounded KV', ''), ('Multimodal', 'vision encoder', '')]),
        *_row(1018, 72, [('NIXL', 'KV transfer API', 'v'), ('NCCL', 'TP / EP collectives', 'v'), ('UCX', 'RDMA transport', 'v'),
                         ('GPUDirect RDMA', 'NIC ↔ GPU', 'v'), ('GPUDirect Storage', 'NVMe ↔ GPU', 'p'), ('KV tiering', 'GPU → host → NVMe', 'p')]),
        *_row(1164, 72, [('HGX H200', 'Hopper · 8 GPUs per server', 'v'), ('HGX B300', 'Blackwell · 8 GPUs per server', 'r'),
                         ('GB200 · GB300 NVL72', 'rack-scale NVLink', 'p'), ('Vera Rubin', 'next generation', 'p')], size=13),
        {'x': _X0 + 20, 'y': 1252, 'w': _X1 - _X0 - 40, 'h': 44, 'label': 'Scale-up fabric  ·  NVLink / NVSwitch, inside a server or an NVL72 rack',
         'style': 'shade', 'size': 12, 'weight': 'normal'},
        {'x': _X0 + 20, 'y': 1310, 'w': _X1 - _X0 - 40, 'h': 44, 'label': 'Scale-out fabric  ·  InfiniBand · Spectrum-X Ethernet (RoCE) · ConnectX SuperNICs',
         'style': 'dark', 'size': 12},
        {'x': 300, 'y': 1394, 'w': 190, 'h': 40, 'label': 'Validated on H200', 'style': 'accent', 'size': 11},
        {'x': 504, 'y': 1394, 'w': 300, 'h': 40, 'label': 'Manifests or reference, not yet run', 'style': 'plain', 'size': 11, 'weight': 'normal'},
        {'x': 818, 'y': 1394, 'w': 120, 'h': 40, 'label': 'Roadmap', 'style': 'ghost', 'size': 11, 'weight': 'normal'},
        {'x': 952, 'y': 1394, 'w': 120, 'h': 40, 'label': 'Generic', 'style': 'soft', 'size': 11, 'weight': 'normal'},
    ],
    'texts': [{'x': 40, 'y': 82 + 18, 'text': 'WHAT THE LAYER DECIDES', 'size': 10.5, 'color': 'muted', 'weight': 'bold'},
              *({**t, 'y': t['y'] + 16} for t in _texts),
              {'x': _X0 + 20, 'y': 782, 'text': 'shared techniques: continuous batching · paged KV cache · chunked prefill · prefix caching · speculative decoding',
               'size': 11, 'color': 'muted'},
              {'x': 1090, 'y': 1404, 'text': 'Status from the recorded studies and ROADMAP.md.', 'size': 11, 'color': 'muted'}],
}

# ----------------------------------------------------------------------------- 1b. control planes
DIAGRAMS['control-planes'] = {
    'size': (1400, 780), 'title': 'Two control planes: NVIDIA Dynamo and llm-d',
    'subtitle': 'Both run SGLang or vLLM workers, split prefill from decode and move KV over NIXL. They differ in where routing and P/D coordination live.',
    'groups': [
        {'x': 40, 'y': 100, 'w': 640, 'h': 580, 'label': 'NVIDIA Dynamo', 'style': 'ghost', 'badge': 'RUN ON H200', 'badge_color': 'accent_ink'},
        {'x': 720, 'y': 100, 'w': 640, 'h': 580, 'label': 'llm-d', 'style': 'ghost', 'badge': 'REFERENCE · NOT YET RUN'},
    ],
    'boxes': [
        {'x': 80, 'y': 150, 'w': 560, 'h': 80, 'label': 'Dynamo frontend', 'sub': 'OpenAI API · tokenization · KV-aware router', 'style': 'accent'},
        {'x': 80, 'y': 384, 'w': 270, 'h': 96, 'label': 'Planner', 'sub': 'SLA autoscaling of\nprefill and decode', 'style': 'soft'},
        {'x': 370, 'y': 384, 'w': 270, 'h': 96, 'label': 'Operator + Grove', 'sub': 'DynamoGraphDeployment\ngang scheduling', 'style': 'soft'},
        {'x': 80, 'y': 260, 'w': 270, 'h': 90, 'label': 'Prefill workers', 'sub': 'SGLang · vLLM · TRT-LLM'},
        {'x': 370, 'y': 260, 'w': 270, 'h': 90, 'label': 'Decode workers', 'sub': 'SGLang · vLLM · TRT-LLM'},
        {'x': 80, 'y': 510, 'w': 560, 'h': 60, 'label': 'Discovery: Kubernetes API (operator default) or etcd', 'style': 'ghost', 'size': 11, 'weight': 'normal'},
        {'x': 80, 'y': 590, 'w': 560, 'h': 60, 'label': 'P/D coordination: the frontend picks both workers', 'style': 'ghost', 'size': 11, 'weight': 'normal'},
        {'x': 760, 'y': 150, 'w': 560, 'h': 80, 'label': 'Gateway (Gateway API)', 'sub': 'Envoy-based gateway + Inference Extension', 'style': 'soft'},
        {'x': 760, 'y': 260, 'w': 560, 'h': 90, 'label': 'Endpoint picker (EPP)', 'sub': 'pluggable scorers: prefix cache, load, P/D decision\nInferencePool selects the model servers', 'style': 'soft'},
        {'x': 760, 'y': 390, 'w': 270, 'h': 80, 'label': 'Prefill pods', 'sub': 'vLLM · SGLang'},
        {'x': 1050, 'y': 390, 'w': 270, 'h': 80, 'label': 'Decode pods', 'sub': 'routing sidecar drives P/D'},
        {'x': 760, 'y': 510, 'w': 560, 'h': 60, 'label': 'Discovery: Kubernetes API (InferencePool, labels)', 'style': 'ghost', 'size': 11, 'weight': 'normal'},
        {'x': 760, 'y': 590, 'w': 560, 'h': 60, 'label': 'P/D coordination: a sidecar on the decode pod calls prefill', 'style': 'ghost', 'size': 11, 'weight': 'normal'},
    ],
    'arrows': [
        {'points': [(215, 230), (215, 260)]},
        {'points': [(505, 230), (505, 260)]},
        {'points': [(350, 305), (370, 305)], 'style': 'accent', 'label': 'KV · NIXL', 'label_at': (360, 365)},
        {'points': [(1185, 350), (1185, 390)]},
        {'points': [(1050, 430), (1030, 430)], 'style': 'accent'},
        {'points': [(1040, 230), (1040, 260)]},
    ],
    'texts': [{'x': 40, 'y': 704, 'text': 'In this repository: Dynamo graphs and lab manifests are measured on H200 (recorded studies);\nllm-d manifests exist for the B300 reference topology (llm-d track, path 05).', 'size': 11, 'color': 'muted'}],
}

# ----------------------------------------------------------------------------- 2. aggregated vs disaggregated
def _timeline(x0, y, kinds):
    out = []
    for i, k in enumerate(kinds):
        out.append({'x': x0 + i * 64, 'y': y, 'w': 60, 'h': 34, 'label': 'prefill' if k == 'P' else 'decode',
                    'style': 'dark' if k == 'P' else 'soft', 'size': 9, 'weight': 'normal'})
    return out


DIAGRAMS['agg-vs-disagg'] = {
    'size': (1400, 780), 'title': 'Aggregated and disaggregated request paths',
    'subtitle': 'Same 16 GPUs either way. Disaggregation moves each request\'s KV cache (and Mamba state for hybrid models) from a prefill worker to a decode worker.',
    'groups': [
        {'x': 40, 'y': 100, 'w': 640, 'h': 640, 'label': 'Aggregated: every worker runs both phases', 'style': 'ghost'},
        {'x': 720, 'y': 100, 'w': 640, 'h': 640, 'label': 'Disaggregated: separate prefill and decode pools', 'style': 'ghost'},
    ],
    'boxes': [
        {'x': 100, 'y': 150, 'w': 130, 'h': 56, 'label': 'Client'},
        {'x': 330, 'y': 150, 'w': 310, 'h': 56, 'label': 'Frontend · KV-aware router'},
        {'x': 100, 'y': 280, 'w': 540, 'h': 160, 'label': 'Aggregated worker', 'sub': 'one batch: new prompts\' prefill chunks run between decode steps', 'style': 'soft'},
        *_timeline(122, 370, 'DDPDDDPD'),
        {'x': 780, 'y': 150, 'w': 130, 'h': 56, 'label': 'Client'},
        {'x': 1010, 'y': 150, 'w': 310, 'h': 56, 'label': 'Frontend · KV-aware router'},
        {'x': 780, 'y': 290, 'w': 214, 'h': 140, 'label': 'Prefill worker', 'sub': 'computes the prompt\'s\nKV cache and Mamba state', 'style': 'accent'},
        {'x': 1106, 'y': 290, 'w': 214, 'h': 140, 'label': 'Decode worker', 'sub': 'generates tokens;\nnever runs prefill', 'style': 'soft'},
    ],
    'arrows': [
        {'points': [(230, 178), (330, 178)], 'label': '1 request', 'label_at': (280, 160)},
        {'points': [(475, 206), (475, 280)], 'label': '2 route', 'label_at': (515, 243)},
        {'points': [(140, 440), (140, 490), (70, 490), (70, 178), (100, 178)], 'label': '3 stream tokens', 'label_at': (205, 505), 'dashed': True},
        {'points': [(910, 178), (1010, 178)], 'label': '1 request', 'label_at': (960, 160)},
        {'points': [(1080, 206), (930, 290)], 'label': '2 prefill', 'label_at': (965, 240)},
        {'points': [(994, 360), (1106, 360)], 'style': 'accent', 'label': '3 KV\n+ state', 'label_at': (1050, 326)},
        {'points': [(1213, 430), (1213, 500), (750, 500), (750, 178), (780, 178)], 'label': '4 stream tokens', 'label_at': (980, 515), 'dashed': True},
    ],
    'texts': [
        {'x': 100, 'y': 560, 'text': 'Measured, 8K in / 128K out, 4 × TP4 (recorded studies):', 'size': 11, 'weight': 'bold'},
        {'x': 100, 'y': 586, 'text': 'prefill chunks stalled running streams for up to 13 s;\nworst inter-token gap 40.4 s; highest output tokens/s.', 'size': 11, 'color': 'muted'},
        {'x': 780, 'y': 445, 'text': 'NIXL over UCX: GPUDirect RDMA on InfiniBand\n(cuda_ipc / NVLink when both workers share a node)', 'size': 10.5, 'color': 'accent_ink'},
        {'x': 780, 'y': 560, 'text': 'Measured, 8K in / 128K out, 1 × TP4 prefill + 3 × TP4 decode:', 'size': 11, 'weight': 'bold'},
        {'x': 780, 'y': 586, 'text': 'no prefill stalls; worst gap 1.1 s; TPOT 14.15 vs 14.51 ms;\n1.34× lower tokens/s (three decode workers, not four).', 'size': 11, 'color': 'muted'},
    ],
}
for g in DIAGRAMS['agg-vs-disagg']['groups']:
    g['h'] = 560
DIAGRAMS['agg-vs-disagg']['size'] = (1400, 700)

# ----------------------------------------------------------------------------- 3. production topology
DIAGRAMS['production-topology'] = {
    'size': (1400, 870), 'title': 'Dynamo production topology on Kubernetes',
    'subtitle': 'What the Dynamo production overlay creates for one model. Arrows show requests (solid), KV transfer (green) and control (dashed).',
    'groups': [
        {'x': 330, 'y': 100, 'w': 760, 'h': 610, 'label': 'Namespace per model · one DynamoGraphDeployment', 'style': 'ghost'},
        {'x': 360, 'y': 290, 'w': 330, 'h': 230, 'label': 'Prefill pool', 'style': 'ghost'},
        {'x': 730, 'y': 290, 'w': 330, 'h': 230, 'label': 'Decode pool', 'style': 'ghost'},
        {'x': 1120, 'y': 100, 'w': 240, 'h': 610, 'label': 'Cluster services', 'style': 'ghost'},
    ],
    'boxes': [
        {'x': 40, 'y': 150, 'w': 130, 'h': 70, 'label': 'Clients', 'sub': 'OpenAI API'},
        {'x': 40, 'y': 285, 'w': 260, 'h': 124, 'label': 'Gateway API · Envoy', 'sub': 'TLS termination\nOIDC / JWT auth\nper-tenant rate limits', 'style': 'soft'},
        {'x': 360, 'y': 150, 'w': 330, 'h': 100, 'label': 'Frontend × 2', 'sub': 'KV-aware router, replica sync\nprobes require discovered workers', 'style': 'accent'},
        {'x': 730, 'y': 150, 'w': 330, 'h': 100, 'label': 'Planner (SLA mode)', 'sub': 'reads TTFT / ITL from Prometheus\nsets prefill and decode replicas', 'style': 'accent'},
        {'x': 380, 'y': 330, 'w': 290, 'h': 70, 'label': 'Prefill worker · TP4', 'sub': 'RDMA device · IPC_LOCK', 'style': 'plain'},
        {'x': 380, 'y': 420, 'w': 290, 'h': 70, 'label': 'Prefill worker · TP4', 'sub': 'scaled by the Planner', 'style': 'ghost'},
        {'x': 750, 'y': 330, 'w': 290, 'h': 50, 'label': 'Decode worker · TP4', 'style': 'plain', 'size': 11},
        {'x': 750, 'y': 390, 'w': 290, 'h': 50, 'label': 'Decode worker · TP4', 'style': 'plain', 'size': 11},
        {'x': 750, 'y': 450, 'w': 290, 'h': 50, 'label': 'Decode worker · TP4', 'style': 'plain', 'size': 11},
        {'x': 360, 'y': 560, 'w': 700, 'h': 60, 'label': 'model-weights PVC (ReadWriteMany)', 'sub': 'staged once by a Job · SHA256SUMS · revision checked by an init container', 'style': 'soft'},
        {'x': 360, 'y': 634, 'w': 700, 'h': 60, 'label': 'Default-deny NetworkPolicies: only the gateway reaches the frontend;\nserving pods reach each other', 'style': 'ghost', 'size': 10.5, 'weight': 'normal'},
        {'x': 1140, 'y': 140, 'w': 200, 'h': 90, 'label': 'Dynamo operator', 'sub': 'reconciles the graph\ninto pods and services', 'style': 'soft'},
        {'x': 1140, 'y': 250, 'w': 200, 'h': 90, 'label': 'Grove + KAI', 'sub': 'gang scheduling of\nprefill and decode', 'style': 'soft'},
        {'x': 1140, 'y': 360, 'w': 200, 'h': 90, 'label': 'Kubernetes API', 'sub': 'worker discovery\n(no etcd, no NATS)', 'style': 'soft'},
        {'x': 1140, 'y': 470, 'w': 200, 'h': 110, 'label': 'Observability', 'sub': 'Prometheus · alert rules\nGrafana · canary', 'style': 'soft'},
        {'x': 40, 'y': 760, 'w': 400, 'h': 80, 'label': 'NVIDIA GPU Operator', 'sub': 'driver + GPUDirect RDMA · GFD labels · DCGM', 'style': 'shade'},
        {'x': 480, 'y': 760, 'w': 420, 'h': 80, 'label': 'NVIDIA Network Operator', 'sub': 'RDMA shared device plugin: rdma/rdma_shared_device_a', 'style': 'shade'},
        {'x': 940, 'y': 760, 'w': 420, 'h': 80, 'label': 'cert-manager', 'sub': 'gateway TLS · operator webhook certificates', 'style': 'shade'},
    ],
    'arrows': [
        {'points': [(105, 220), (105, 290)]},
        {'points': [(300, 345), (330, 345), (330, 200), (360, 200)], 'label': 'HTTPS', 'label_at': (318, 180)},
        {'points': [(525, 250), (525, 330)]},
        {'points': [(640, 250), (895, 290)]},
        {'points': [(670, 365), (750, 365)], 'style': 'accent', 'label': 'NIXL', 'label_at': (710, 350)},
        {'points': [(1060, 200), (1140, 185)], 'dashed': True, 'label': 'scale', 'label_at': (1100, 175)},
        {'points': [(1140, 500), (1060, 500)], 'dashed': True, 'style': 'muted'},
    ],
}

# ----------------------------------------------------------------------------- 4. decision flow
_q = lambda x, y, w, text: {'x': x, 'y': y, 'w': w, 'h': 74, 'label': text, 'style': 'shade', 'size': 12}
DIAGRAMS['decision-flow'] = {
    'size': (1400, 1010), 'title': 'Choosing a topology, engine and control plane',
    'subtitle': 'Answer the questions in order. Any "no" on the left means aggregated replicas with KV-aware routing.',
    'boxes': [
        {'x': 40, 'y': 100, 'w': 660, 'h': 60, 'label': 'Workload: ISL and OSL distributions, request rate, p99 TTFT and ITL targets', 'style': 'plain'},
        _q(40, 200, 660, 'Are prefill and decode both a large share of GPU time,\nat the same time, at your peak load?'),
        _q(40, 320, 660, 'Is p99 inter-token latency a hard SLO?'),
        _q(40, 440, 660, 'Can you tune the P:D ratio? (4+ nodes, or several\nworkers per node, e.g. TP2/TP4 on 8-GPU nodes)'),
        _q(40, 560, 660, 'Is there an RDMA fabric (InfiniBand or RoCE)\nor an NVLink domain for KV transfer?'),
        {'x': 40, 'y': 690, 'w': 660, 'h': 64, 'label': 'Aggregated: KV transfer over TCP would cost more than it saves', 'style': 'soft', 'size': 11.5},
        {'x': 820, 'y': 200, 'w': 540, 'h': 194, 'label': 'Aggregated replicas + KV-aware router', 'sub':
         'simplest to run, best TTFT at low load,\nall GPUs prefill and decode.\nTune chunked prefill to bound decode stalls.\nOn 2 × HGX H200 with TP8 workers this is\nusually the right answer (recorded studies).', 'style': 'soft'},
        {'x': 820, 'y': 560, 'w': 540, 'h': 100, 'label': 'Disaggregated, Planner-managed P:D', 'sub': 'prefill and decode pools sized for the SLO;\nconfirm with a goodput sweep (planned study 01)', 'style': 'accent'},
        _q(820, 700, 540, 'MoE or MLA model (DeepSeek-class, Nemotron Ultra)?'),
        {'x': 820, 'y': 814, 'w': 540, 'h': 76, 'label': 'Per-phase parallelism', 'sub': 'prefill: TP2–TP4 (+EP) · decode: wide EP + DP attention, MTP', 'style': 'accent'},
        {'x': 40, 'y': 830, 'w': 660, 'h': 60, 'label': 'Engine: SGLang · vLLM · TensorRT-LLM, by model support and features', 'style': 'plain', 'size': 11.5},
        {'x': 40, 'y': 910, 'w': 1320, 'h': 60, 'label': 'Control plane: Dynamo operator (graphs, Planner, KV router) on Kubernetes, or llm-d (Gateway API Inference Extension)', 'style': 'plain', 'size': 11.5},
    ],
    'arrows': [
        {'points': [(370, 160), (370, 200)]},
        {'points': [(370, 274), (370, 320)], 'label': 'yes', 'label_at': (395, 297)},
        {'points': [(370, 394), (370, 440)], 'label': 'yes', 'label_at': (395, 417)},
        {'points': [(370, 514), (370, 560)], 'label': 'yes', 'label_at': (395, 537)},
        {'points': [(370, 634), (370, 690)], 'label': 'no', 'label_at': (390, 662)},
        {'points': [(700, 237), (820, 237)], 'label': 'no', 'label_at': (760, 222)},
        {'points': [(700, 357), (820, 357)], 'label': 'no', 'label_at': (760, 342)},
        {'points': [(700, 477), (760, 477), (760, 380), (820, 380)], 'label': 'no', 'label_at': (735, 462)},
        {'points': [(700, 597), (820, 597)], 'label': 'yes', 'label_at': (760, 582), 'style': 'accent'},
        {'points': [(1090, 660), (1090, 700)]},
        {'points': [(1090, 774), (1090, 814)], 'label': 'yes', 'label_at': (1115, 794)},
    ],
}

# ----------------------------------------------------------------------------- 5. when disaggregation wins
DIAGRAMS['when-disaggregation-wins'] = {
    'size': (1400, 830), 'title': 'When disaggregation wins',
    'subtitle': 'Design guidance with the three measured H200 studies placed on it. Region boundaries are qualitative; experiment 01 measures them.',
    'boxes': [
        {'x': 160, 'y': 120, 'w': 360, 'h': 640, 'align': 'top', 'label': 'Low load', 'sub': 'room in every batch: aggregated has\nthe best TTFT and the fewest moving parts', 'style': 'soft'},
        {'x': 530, 'y': 120, 'w': 820, 'h': 200, 'align': 'top', 'label': 'High load, prefill-dominated', 'sub': 'aggregated prefills on every GPU;\na fixed prefill pool caps prefill throughput', 'style': 'shade'},
        {'x': 530, 'y': 330, 'w': 820, 'h': 220, 'align': 'top', 'label': 'High load, both phases substantial', 'sub': 'disaggregation can win on goodput at a tight ITL SLO when P:D is tunable\nUNVALIDATED here: planned study 01-pd-ratio-sweep', 'style': 'accent'},
        {'x': 530, 'y': 560, 'w': 820, 'h': 200, 'align': 'top', 'label': 'High load, decode-dominated', 'sub': 'aggregated wins on tokens/s; disaggregated removes prefill stalls\nfrom the tail ITL. Which matters depends on the SLO.', 'style': 'shade'},
    ],
    'arrows': [
        {'points': [(160, 780), (1350, 780)], 'label': 'offered load (requests in flight, requests/s) →', 'label_at': (755, 800)},
        {'points': [(140, 760), (140, 120)]},
    ],
    'texts': [
        {'x': 40, 'y': 430, 'text': 'prefill share\nof GPU time\n(ISL vs OSL)', 'size': 11, 'color': 'muted'},
        {'x': 940, 'y': 430, 'text': 'A tighter ITL SLO widens this band: prefill stalls\nin aggregated batches become SLO misses.', 'size': 10.5, 'color': 'accent_ink', 'ha': 'center'},
    ],
    'points': [
        {'x': 190, 'y': 300, 'label': 'Nemotron 3 Nano, 128K in / 256 out,\n4 in flight: aggregated 1.62× faster'},
        {'x': 190, 'y': 390, 'label': 'DeepSeek V4 Pro, 256K in, 4 in flight:\naggregated 5.5× faster;\nPD follow-ups lost prefix reuse'},
        {'x': 800, 'y': 700, 'label': 'Nemotron 3 Nano, 8K in / 128K out, 384–512 in flight:\naggregated 1.34× tokens/s; worst ITL 40.4 s vs 1.1 s', 'style': 'accent'},
    ],
}

# ----------------------------------------------------------------------------- 6. P:D and per-phase parallelism
DIAGRAMS['pd-parallelism'] = {
    'size': (1400, 770), 'title': 'P:D ratio and per-phase parallelism for MoE and MLA models',
    'subtitle': 'Prefill and decode stress different resources, so each pool gets its own parallelism. Design guidance; see notes for what is measured.',
    'groups': [
        {'x': 40, 'y': 100, 'w': 560, 'h': 520, 'label': 'Prefill pool: compute-bound', 'style': 'ghost'},
        {'x': 800, 'y': 100, 'w': 560, 'h': 520, 'label': 'Decode pool: memory-bandwidth-bound', 'style': 'ghost'},
    ],
    'boxes': [
        {'x': 70, 'y': 150, 'w': 500, 'h': 96, 'label': 'Small TP per worker (TP2–TP4)', 'sub': 'more workers prefill in parallel; long prompts\nsplit across fewer GPUs per worker', 'style': 'soft'},
        {'x': 70, 'y': 266, 'w': 500, 'h': 96, 'label': 'Chunked prefill', 'sub': '4K–16K token chunks; larger chunks lower TTFT\nfor 128K+ prompts (planned study 07)', 'style': 'soft'},
        {'x': 70, 'y': 382, 'w': 500, 'h': 96, 'label': 'Expert parallelism for MoE (optional)', 'sub': 'experts spread across the prefill GPUs', 'style': 'soft'},
        {'x': 830, 'y': 150, 'w': 500, 'h': 96, 'label': 'Wide expert parallelism (EP)', 'sub': 'each GPU holds a slice of the experts;\nall-to-all dispatch every decode step', 'style': 'accent'},
        {'x': 830, 'y': 266, 'w': 500, 'h': 96, 'label': 'DP attention for MLA', 'sub': 'each rank keeps whole sequences\' latent KV:\nno KV duplication across TP ranks', 'style': 'accent'},
        {'x': 830, 'y': 382, 'w': 500, 'h': 96, 'label': 'MTP / speculative decoding', 'sub': 'DeepSeek V4: EAGLE (topk 1) with the NextN head;\nSGLang 0.5.16 also allows DSPARK', 'style': 'accent'},
        {'x': 70, 'y': 498, 'w': 500, 'h': 96, 'label': 'Bottleneck: TTFT under load', 'sub': 'queueing for prefill when the pool is too small', 'style': 'ghost', 'weight': 'normal'},
        {'x': 830, 'y': 498, 'w': 500, 'h': 96, 'label': 'Bottleneck: ITL and batch size', 'sub': 'KV capacity and HBM bandwidth per step', 'style': 'ghost', 'weight': 'normal'},
        {'x': 620, 'y': 240, 'w': 160, 'h': 156, 'label': 'P : D', 'sub': 'ratio follows\nISL × rate vs\nOSL × rate\nand the SLO', 'style': 'plain'},
    ],
    'arrows': [
        {'points': [(600, 430), (800, 430)], 'style': 'accent', 'label': 'KV transfer (NIXL)', 'label_at': (700, 412)},
    ],
    'texts': [
        {'x': 40, 'y': 650, 'text': 'The Dynamo Planner adjusts prefill and decode replicas within one GPU budget (max_gpu_budget); it has no per-role cap in 1.4.0.', 'size': 11, 'color': 'muted'},
        {'x': 40, 'y': 680, 'text': 'Measured on the H200 site: TP8 and TP4 layouts only (recorded studies). DP attention + EP and MTP for DeepSeek V4 Pro are experiment 05.', 'size': 11, 'color': 'muted'},
        {'x': 40, 'y': 710, 'text': 'Do not size a 30B-A3B model like Nemotron 3 Nano at TP8: its weights fit on one GPU; TP2–TP4 workers leave room to tune P:D.', 'size': 11, 'color': 'muted'},
    ],
}


# ----------------------------------------------------------------------------- 7/8. site topologies
def _node(x, y, name, gpu, extra_box, hca0=0):
    boxes = [{'x': x + 24 + (i % 4) * 128, 'y': y + 60 + (i // 4) * 70, 'w': 116, 'h': 58, 'label': gpu, 'sub': f'GPU {i}',
              'style': 'soft', 'size': 11} for i in range(8)]
    boxes.append({'x': x + 24, 'y': y + 210, 'w': 500, 'h': 40, 'label': 'NVLink / NVSwitch (all-to-all within the node)', 'style': 'shade', 'size': 10.5, 'weight': 'normal'})
    # HCA names as recorded in UCX_NET_DEVICES / IB_DEVICES; link speed is not recorded.
    boxes += [{'x': x + 24 + i * 63, 'y': y + 270, 'w': 56, 'h': 48, 'label': f'mlx5\n_{hca0 + i}', 'style': 'plain', 'size': 9}
              for i in range(8)]
    boxes.append(extra_box(x, y))
    return boxes


DIAGRAMS['h200-site'] = {
    'size': (1400, 780), 'title': 'Validated site: 2 × HGX H200 on managed Kubernetes',
    'subtitle': 'Every measured result in the recorded studies comes from this site. Workers used hostNetwork in the lab; the production overlay uses the RDMA device plugin instead.',
    'groups': [
        {'x': 40, 'y': 110, 'w': 560, 'h': 420, 'label': 'Node A', 'style': 'ghost', 'badge': 'VALIDATED', 'badge_color': 'accent_ink'},
        {'x': 800, 'y': 110, 'w': 560, 'h': 420, 'label': 'Node B', 'style': 'ghost', 'badge': 'VALIDATED', 'badge_color': 'accent_ink'},
    ],
    'boxes': [
        *_node(40, 110, 'H200 141 GB', 'H200', lambda x, y: {'x': x + 24, 'y': y + 340, 'w': 500, 'h': 62, 'label': 'Network SSD 1500Gi (RWO)', 'sub': 'weights for both models', 'style': 'shade', 'size': 11}),
        *_node(800, 110, 'H200 141 GB', 'H200', lambda x, y: {'x': x + 24, 'y': y + 340, 'w': 500, 'h': 62, 'label': 'Network SSD 1500Gi (RWO)', 'sub': 'weights for both models', 'style': 'shade', 'size': 11}),
        {'x': 620, 'y': 360, 'w': 160, 'h': 90, 'label': 'InfiniBand', 'sub': '8 HCAs per node\nNIXL / UCX', 'style': 'accent'},
        {'x': 40, 'y': 566, 'w': 1320, 'h': 176, 'label': 'Measured layouts (16 GPUs each)', 'sub':
         'DeepSeek V4 Pro, 256K in: 2 × TP8 aggregated · 1 × TP8 prefill + 1 × TP8 decode\n'
         'Nemotron 3 Nano, 128K in / 256 out: 2 × TP8 aggregated · 1 × TP8 prefill + 1 × TP8 decode\n'
         'Nemotron 3 Nano, 8K in / 128K out: 4 × TP4 aggregated (512 in flight) · 1 × TP4 prefill + 3 × TP4 decode (384 in flight)\n\n'
         'Lab control plane: one Dynamo frontend and a single etcd on node A; in-cluster CPU benchmark client.', 'style': 'plain'},
    ],
    'arrows': [
        {'points': [(564, 405), (620, 405)], 'style': 'accent', 'both': True},
        {'points': [(780, 405), (824, 405)], 'style': 'accent', 'both': True},
    ],
}

DIAGRAMS['b300-reference'] = {
    'size': (1400, 780), 'title': 'Reference topology: 2 × HGX B300 (UNVALIDATED)',
    'subtitle': 'Manifests for tracks 01–04 exist and pass offline tests. No run on this hardware is recorded; validation is planned study 09.',
    'groups': [
        {'x': 40, 'y': 110, 'w': 560, 'h': 420, 'label': 'Node A', 'style': 'ghost', 'badge': 'UNVALIDATED'},
        {'x': 800, 'y': 110, 'w': 560, 'h': 420, 'label': 'Node B', 'style': 'ghost', 'badge': 'UNVALIDATED'},
    ],
    'boxes': [
        *_node(40, 110, 'B300', 'B300', lambda x, y: {'x': x + 24, 'y': y + 340, 'w': 500, 'h': 62, 'label': 'Local NVMe', 'sub': 'pinned model revision', 'style': 'shade', 'size': 11}, hca0=4),
        *_node(800, 110, 'B300', 'B300', lambda x, y: {'x': x + 24, 'y': y + 340, 'w': 500, 'h': 62, 'label': 'Local NVMe', 'sub': 'pinned model revision', 'style': 'shade', 'size': 11}, hca0=4),
        {'x': 620, 'y': 360, 'w': 160, 'h': 90, 'label': 'InfiniBand', 'sub': '8 HCAs per node', 'style': 'ghost'},
        {'x': 40, 'y': 570, 'w': 1320, 'h': 170, 'label': 'Planned tracks (Nemotron 3 Ultra 550B-A55B NVFP4)', 'sub':
         '01 aggregated (vLLM, SGLang) · 02 Dynamo P/D on vLLM · 03 Dynamo P/D on SGLang · 04 llm-d P/D\n'
         'Each track: deploy, verify, prove RDMA transfer with IB counters, benchmark, tear down.', 'style': 'ghost'},
    ],
    'arrows': [
        {'points': [(564, 405), (620, 405)], 'style': 'muted', 'dashed': True},
        {'points': [(780, 405), (824, 405)], 'style': 'muted', 'dashed': True},
    ],
}

# ----------------------------------------------------------------------------- 9. KV cache tiers
_tiers = [('G1  GPU HBM', 'active KV pages for running requests', 'in use on every engine', 'accent'),
          ('G2  Host DRAM', 'offloaded prefixes, seconds to reload', 'roadmap (KV offloading phase 1)', 'soft'),
          ('G3  Local NVMe · GPUDirect Storage', 'large working sets per node', 'roadmap (phase 2)', 'soft'),
          ('G4  Shared storage', 'prefixes reused across nodes', 'roadmap (phase 3)', 'soft')]
DIAGRAMS['kv-cache-hierarchy'] = {
    'size': (1400, 640), 'title': 'KV cache tiers',
    'subtitle': 'Each tier down holds more KV and takes longer to bring back into HBM. Only G1 is used by the measured deployments.',
    'boxes': [b for i, (name, role, status, style) in enumerate(_tiers) for b in (
        {'x': 40, 'y': 130 + i * 104, 'w': 520 + i * 90, 'h': 84, 'label': name, 'sub': role, 'style': style, 'size': 13},
        {'x': 960, 'y': 130 + i * 104, 'w': 400, 'h': 84, 'label': status, 'style': 'ghost', 'size': 11, 'weight': 'normal'})],
    'arrows': [{'points': [(920, 140), (920, 540)]}],
    'texts': [{'x': 960, 'y': 104, 'text': 'Status in this repository', 'size': 11, 'color': 'muted', 'weight': 'bold'},
              {'x': 40, 'y': 570, 'text': 'Down the arrow: more capacity per byte of cost, higher latency to reload a prefix. Plan: ROADMAP.md, KV-cache offloading phases 0-3.',
               'size': 11, 'color': 'muted'}],
}

# ----------------------------------------------------------------------------- 10. KV transfer datapath
DIAGRAMS['kv-transfer-datapath'] = {
    'size': (1400, 600), 'title': 'KV transfer datapath between nodes',
    'subtitle': 'GPUDirect RDMA moves KV pages from prefill HBM to decode HBM without a host copy. Staging through host memory works but is slower.',
    'groups': [
        {'x': 40, 'y': 100, 'w': 520, 'h': 400, 'label': 'Prefill node', 'style': 'ghost'},
        {'x': 840, 'y': 100, 'w': 520, 'h': 400, 'label': 'Decode node', 'style': 'ghost'},
    ],
    'boxes': [
        {'x': 70, 'y': 150, 'w': 460, 'h': 60, 'label': 'SGLang / vLLM → NIXL → UCX (rc, cuda_copy, cuda_ipc)', 'style': 'soft', 'size': 11},
        {'x': 70, 'y': 240, 'w': 200, 'h': 80, 'label': 'GPU HBM', 'sub': 'KV pages', 'style': 'accent'},
        {'x': 330, 'y': 240, 'w': 200, 'h': 80, 'label': 'IB NIC (mlx5)', 'sub': 'GPUDirect RDMA'},
        {'x': 70, 'y': 380, 'w': 460, 'h': 70, 'label': 'Host DRAM', 'sub': 'fallback staging', 'style': 'ghost'},
        {'x': 870, 'y': 150, 'w': 460, 'h': 60, 'label': 'UCX → NIXL → SGLang / vLLM', 'style': 'soft', 'size': 11},
        {'x': 1130, 'y': 240, 'w': 200, 'h': 80, 'label': 'GPU HBM', 'sub': 'KV pages', 'style': 'accent'},
        {'x': 870, 'y': 240, 'w': 200, 'h': 80, 'label': 'IB NIC (mlx5)', 'sub': 'GPUDirect RDMA'},
        {'x': 870, 'y': 380, 'w': 460, 'h': 70, 'label': 'Host DRAM', 'sub': 'fallback staging', 'style': 'ghost'},
        {'x': 600, 'y': 250, 'w': 200, 'h': 60, 'label': 'InfiniBand switch', 'style': 'shade'},
    ],
    'arrows': [
        {'points': [(270, 280), (330, 280)], 'style': 'accent'},
        {'points': [(530, 280), (600, 280)], 'style': 'accent'},
        {'points': [(800, 280), (870, 280)], 'style': 'accent'},
        {'points': [(1070, 280), (1130, 280)], 'style': 'accent'},
        {'points': [(170, 320), (170, 380)], 'dashed': True, 'style': 'muted'},
        {'points': [(1230, 380), (1230, 320)], 'dashed': True, 'style': 'muted'},
    ],
    'texts': [
        {'x': 40, 'y': 530, 'text': 'Prerequisites: GPU Operator with driver.rdma.enabled; RDMA device plugin; IPC_LOCK; UCX_NET_DEVICES naming the IB HCAs.', 'size': 11, 'color': 'muted'},
        {'x': 40, 'y': 556, 'text': 'Proof of transfer: InfiniBand port counters rise on both nodes and sglang:kv_transfer_total_mb is non-zero (dashboard panel).', 'size': 11, 'color': 'muted'},
    ],
}
