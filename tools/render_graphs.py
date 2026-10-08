#!/usr/bin/env python3
"""Render the operator-managed DynamoGraphDeployment (nvidia.com/v1beta1) graphs.

    python tools/render_graphs.py          # writes tracks/nvidia-dynamo/graphs/<model>/{aggregated,disaggregated}/

Each model has ONE graph name; the aggregated and disaggregated variants differ only
in the worker components, so switching topology is an edit of one custom resource
(`kubectl apply -k` of the other variant updates the same object). Engine flags start
from the configuration measured in tracks/nvidia-dynamo/studies/ (the lab manifests under
tracks/nvidia-dynamo/sites/nebius-h200-2x8/<model>/lab/as-measured) and add only the reliability
mitigations listed in MITIGATIONS. tests/test_graphs.py enforces that.

Every field used here is verified against Dynamo v1.4.0 and SGLang v0.5.16; see
reference/upstream-verification.md.
"""
import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tracks/nvidia-dynamo/graphs'

SGLANG_IMAGE = ('nvcr.io/nvidia/ai-dynamo/sglang-runtime:1.4.0'
                '@sha256:314bda9534498899ad855f8c72434f4015660521665025a587e73486b74917f3')
BUSYBOX_IMAGE = 'busybox:1.37.0@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e'
ITL_BUCKETS = [str(round(0.001 * i, 3)) for i in range(1, 41)] + [
    '0.045', '0.05', '0.06', '0.08', '0.1', '0.15', '0.2', '0.3', '0.5', '1.0', '2.0', '5.0', '10.0']

# Flags added on top of the measured configuration, and why. Anything else that
# differs from the lab manifests fails tests/test_graphs.py.
MITIGATIONS = {
    '--gc-threshold': 'raise CPython GC thresholds so generation-2 collections (0.34-0.45 s '
                      'output pauses every ~11 s in the 8K/128K study) run ~100x less often; '
                      'confirmed by tracks/nvidia-dynamo/studies/planned/04-reliability',
    '--router-min-initial-workers': 'frontend waits for every worker before routing, so the first '
                                    'registered worker does not absorb the initial burst',
    '--router-decode-active-request-weight': 'count active requests in the KV-router cost; with unique '
                                             'prompts the default (0) balances on tokens only and produced '
                                             '152/120/120/120 in the 8K/128K study',
    '--router-replica-sync': 'two frontend replicas share router state',
    '--max-running-requests (prefill)': 'cap concurrent prefill requests to bound host staging memory; the '
                                        'prefill pod swung 104-308 GiB during a 384-request burst and was '
                                        'OOM-killed at its 384 GiB limit (8K/128K diagnostics)',
    '--kv-events-config': 'fixed in-pod port 5557; the lab used per-node host ports because of hostNetwork',
}

COMMON_ENV = [
    {'name': 'PYTHONHASHSEED', 'value': '0'},
    {'name': 'HF_HUB_OFFLINE', 'value': '1'},
    {'name': 'TRANSFORMERS_OFFLINE', 'value': '1'},
    {'name': 'HF_HOME', 'value': '/runtime/hf'},
    {'name': 'HF_MODULES_CACHE', 'value': '/runtime/hf_modules'},
    {'name': 'XDG_CACHE_HOME', 'value': '/runtime/cache'},
    {'name': 'TRITON_CACHE_DIR', 'value': '/runtime/triton'},
    {'name': 'TORCH_EXTENSIONS_DIR', 'value': '/runtime/torch_extensions'},
    {'name': 'SGLANG_JIT_DEEPGEMM_PRECOMPILE', 'value': '0'},
    {'name': 'SGLANG_JIT_DEEPGEMM_FAST_WARMUP', 'value': '1'},
    # NIXL/UCX over InfiniBand. UCX_NET_DEVICES is set per site (production overlay).
    {'name': 'UCX_TLS', 'value': 'rc,cuda_copy,cuda_ipc,sm,self'},
    {'name': 'UCX_RNDV_SCHEME', 'value': 'get_zcopy'},
    # Opt-in GC freeze hook (tracks/nvidia-dynamo/common/sitecustomize.py); empty = disabled.
    {'name': 'PYTHONPATH', 'value': '/opt/serving-hooks'},
    {'name': 'SERVING_GC_FREEZE_AFTER_S', 'value': ''},
]

PROFILES = {
    'nemotron-3-nano': {
        'model_id': 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16',
        'revision': 'bf77c3174f68ad409e1c2aa60daeb46e32d1c606',
        'weights_subpath': '.models/nemotron-3-nano-bf16',
        'gpus_per_worker': 4,
        'measured': 'tracks/nvidia-dynamo/studies/nemotron-3-nano-8k-128k-comparison (TP4, 262144 context)',
        'engine': [
            '--tensor-parallel-size', '4', '--trust-remote-code', '--context-length', '262144',
            '--chunked-prefill-size', '4096', '--mem-fraction-static', '0.88', '--page-size', '1',
            '--kv-cache-dtype', 'auto', '--enable-metrics', '--disable-piecewise-cuda-graph',
            '--weight-loader-prefetch-checkpoints', '--attention-backend', 'flashinfer',
            # Hybrid Mamba: no_buffer is what was measured; SGLang 0.5.16 forces overlap
            # scheduling off with it (arg_groups/overrides.py L1158-1201).
            '--mamba-radix-cache-strategy', 'no_buffer', '--disable-overlap-schedule',
            '--bucket-inter-token-latency', *ITL_BUCKETS,
        ],
        'decode_running': '136', 'prefill_running': '32',
        'aggregated': {'workers': 4},
        'disaggregated': {'prefill': 1, 'decode': 3},
        'memory': {'worker': ('96Gi', '256Gi'), 'prefill': ('128Gi', '448Gi'), 'decode': ('64Gi', '192Gi')},
        'shm': '96Gi', 'cpu': '28', 'active_request_weight': '8000',
    },
    'deepseek-v4-pro': {
        'model_id': 'deepseek-ai/DeepSeek-V4-Pro-0813',
        'revision': None,  # read from the measured run record; see tracks/nvidia-dynamo/sites/.../deepseek-v4-pro
        'weights_subpath': '',
        'gpus_per_worker': 8,
        'measured': 'tracks/nvidia-dynamo/studies/deepseek-v4-pro-256k-comparison (TP8, 262144 context)',
        'engine': [
            '--tensor-parallel-size', '8', '--trust-remote-code', '--context-length', '262144',
            '--chunked-prefill-size', '4096', '--mem-fraction-static', '0.88', '--page-size', '256',
            '--kv-cache-dtype', 'fp8_e4m3', '--moe-runner-backend', 'marlin', '--enable-metrics',
            '--disable-piecewise-cuda-graph', '--dyn-tool-call-parser', 'deepseek_v4',
            '--dyn-reasoning-parser', 'deepseek_v4', '--weight-loader-prefetch-checkpoints',
        ],
        'decode_running': '4', 'prefill_running': '4',
        'aggregated': {'workers': 2},
        'disaggregated': {'prefill': 1, 'decode': 1},
        'memory': {'worker': ('512Gi', '1300Gi'), 'prefill': ('512Gi', '1300Gi'), 'decode': ('512Gi', '1300Gi')},
        'shm': '128Gi', 'cpu': '32', 'active_request_weight': '0',
    },
}


def deepseek_revision():
    import json
    record = ROOT / 'tracks/nvidia-dynamo/sites/nebius-h200-2x8/deepseek-v4-pro/lab/as-measured/records/deployment.json'
    return json.loads(record.read_text())['model']['revision']


def with_tp(p, tp):
    """Profile copy with a different tensor-parallel size (engine flag and GPU count)."""
    q = copy.deepcopy(p)
    i = q['engine'].index('--tensor-parallel-size')
    q['engine'][i + 1] = str(tp)
    q['gpus_per_worker'] = tp
    return q


def worker_container(p, role):
    running = p['decode_running'] if role in ('worker', 'decode') else p['prefill_running']
    args = ['-m', 'dynamo.sglang', '--model-path', '/model', '--served-model-name', p['model_id'],
            *p['engine'], '--max-running-requests', running,
            '--host', '0.0.0.0', '--port', '30000',
            '--gc-threshold', '7000', '10', '100',
            '--kv-events-config', '{"publisher":"zmq","topic":"kv-events","endpoint":"tcp://*:5557"}']
    if role == 'prefill':
        args += ['--disaggregation-mode', 'prefill', '--disaggregation-transfer-backend', 'nixl',
                 '--disaggregation-bootstrap-port', '8998', '--disable-cuda-graph']
    else:
        args += ['--cuda-graph-max-bs-decode', running]
    if role == 'decode':
        args += ['--disaggregation-mode', 'decode', '--disaggregation-transfer-backend', 'nixl',
                 '--disaggregation-bootstrap-port', '8998']
    request, limit = p['memory'][role]
    gpus = str(p['gpus_per_worker'])
    weights = {'name': 'model-weights', 'mountPath': '/model', 'readOnly': True}
    if p['weights_subpath']:
        weights['subPath'] = p['weights_subpath']
    return {
        'name': 'main', 'image': SGLANG_IMAGE, 'command': ['python3'], 'args': args,
        'env': copy.deepcopy(COMMON_ENV),
        'resources': {'requests': {'cpu': p['cpu'], 'memory': request, 'nvidia.com/gpu': gpus},
                      'limits': {'memory': limit, 'nvidia.com/gpu': gpus}},
        # RDMA verbs need locked memory; no privileged mode and no hostNetwork. RDMA
        # devices arrive through a device-plugin resource added per site.
        'securityContext': {'capabilities': {'add': ['IPC_LOCK']}},
        # Large checkpoints and kernel compilation take tens of minutes: a 2 h startup
        # window, then a lenient liveness so a long prefill burst never trips a restart.
        'startupProbe': {'httpGet': {'path': '/live', 'port': 9090}, 'periodSeconds': 10, 'failureThreshold': 720},
        'livenessProbe': {'httpGet': {'path': '/live', 'port': 9090}, 'periodSeconds': 30,
                          'timeoutSeconds': 10, 'failureThreshold': 6},
        'readinessProbe': {'httpGet': {'path': '/health', 'port': 9090}, 'periodSeconds': 10,
                           'timeoutSeconds': 5, 'failureThreshold': 3},
        'volumeMounts': [weights, {'name': 'runtime', 'mountPath': '/runtime'},
                         {'name': 'python-hooks', 'mountPath': '/opt/serving-hooks', 'readOnly': True}],
    }


def verify_weights(p, revision):
    marker = f'/model/{p["weights_subpath"]}/DEPLOYED_REVISION'.replace('//', '/')
    check = (f'test -f {marker} || {{ echo "missing {marker}"; exit 1; }}; '
             f'got=$(cat {marker}); [ "$got" = "{revision}" ] || '
             f'{{ echo "weights revision $got != pinned {revision}"; exit 1; }}; '
             'if [ "$VERIFY_WEIGHTS" = full ] && [ -f "$(dirname ' + marker + ')/SHA256SUMS" ]; then '
             'cd "$(dirname ' + marker + ')" && sha256sum -c SHA256SUMS; fi')
    return {'name': 'verify-weights', 'image': BUSYBOX_IMAGE, 'command': ['sh', '-c', check],
            'env': [{'name': 'VERIFY_WEIGHTS', 'value': 'marker'}],
            'volumeMounts': [{'name': 'model-weights', 'mountPath': '/model', 'readOnly': True}]}


def worker_component(p, name, role, replicas, revision):
    return {
        'name': name, 'type': role, 'replicas': replicas, 'sharedMemorySize': p['shm'],
        'podTemplate': {'spec': {
            'initContainers': [verify_weights(p, revision)],
            'containers': [worker_container(p, role)],
            'volumes': [
                {'name': 'model-weights', 'persistentVolumeClaim': {'claimName': 'model-weights', 'readOnly': True}},
                {'name': 'runtime', 'emptyDir': {}},
                {'name': 'python-hooks', 'configMap': {'name': 'dynamo-python-hooks'}},
            ],
        }},
    }


def frontend(p, workers, disaggregated):
    probe = lambda mode: {'exec': {'command': ['python3', '/opt/probe/frontend_probe.py', mode]},
                          'periodSeconds': 10, 'timeoutSeconds': 5, 'failureThreshold': 3}
    return {
        'name': 'Frontend', 'type': 'frontend', 'replicas': 2,
        'podTemplate': {'spec': {
            'containers': [{
                'name': 'main', 'image': SGLANG_IMAGE, 'command': ['python3'],
                'args': ['-m', 'dynamo.frontend', '--http-port', '8000', '--router-mode', 'kv',
                         '--router-min-initial-workers', str(workers),
                         '--router-decode-active-request-weight', p['active_request_weight'],
                         '--router-replica-sync'],
                'env': [{'name': 'PROBE_REQUIRE', 'value': 'backend,prefill' if disaggregated else 'backend'},
                        {'name': 'PROBE_LOSS_GRACE_S', 'value': '300'}],
                'resources': {'requests': {'cpu': '4', 'memory': '16Gi'}, 'limits': {'memory': '64Gi'}},
                'readinessProbe': probe('ready'), 'livenessProbe': probe('live'),
                'volumeMounts': [{'name': 'probe', 'mountPath': '/opt/probe', 'readOnly': True}],
            }],
            'volumes': [{'name': 'probe', 'configMap': {'name': 'dynamo-frontend-probe'}}],
        }},
    }


def graph(model, p, topology, layout=None, extra_args=None):
    """layout overrides replica counts and TP per role, e.g. {'prefill': (2, 2), 'decode': (3, 4)}
    or {'workers': (8, 2)}; extra_args maps a role to engine flags appended for experiments."""
    revision = p['revision'] or deepseek_revision()
    layout, extra_args = layout or {}, extra_args or {}

    def role(name, comp_type, default_n):
        n, tp = layout.get(name, (default_n, p['gpus_per_worker']))
        c = worker_component(with_tp(p, tp), name, comp_type, n, revision)
        c['podTemplate']['spec']['containers'][0]['args'] += list(extra_args.get(name, []))
        return c, n

    if topology == 'aggregated':
        w, routed = role('worker', 'worker', p['aggregated']['workers'])
        workers = [w]
    else:
        d = p['disaggregated']
        pre, _ = role('prefill', 'prefill', d['prefill'])
        dec, routed = role('decode', 'decode', d['decode'])
        workers = [pre, dec]
    return {
        'apiVersion': 'nvidia.com/v1beta1', 'kind': 'DynamoGraphDeployment',
        'metadata': {'name': model, 'annotations': {
            'serving-solutions/topology': topology,
            'serving-solutions/model-revision': revision,
            'serving-solutions/measured-baseline': p['measured']}},
        'spec': {'backendFramework': 'sglang',
                 'components': [frontend(p, routed, topology == 'disaggregated'), *workers]},
    }


HEADER = ('# Generated by tools/render_graphs.py — edit the profile there, not this file.\n'
          '# One graph name per model: applying the other topology variant edits this same\n'
          '# DynamoGraphDeployment, and the Dynamo operator reconciles the difference.\n')


def main():
    for model, p in PROFILES.items():
        for topology in ('aggregated', 'disaggregated'):
            d = OUT / model / topology
            d.mkdir(parents=True, exist_ok=True)
            (d / 'graph.yaml').write_text(HEADER + yaml.safe_dump(graph(model, p, topology), sort_keys=False, width=110))
            (d / 'kustomization.yaml').write_text(
                'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n'
                f'namespace: {model}\nresources:\n- graph.yaml\ncomponents:\n- ../../../common\n')
            print('wrote', d.relative_to(OUT.parent.parent.parent) if OUT.is_relative_to(ROOT) else d)


if __name__ == '__main__':
    main()
