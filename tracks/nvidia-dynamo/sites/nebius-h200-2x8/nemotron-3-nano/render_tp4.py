"""Render the TP4 long-decode worker manifests from the TP8 aggregated manifest.

Two 4-GPU workers share each node's host network, so the second worker on a
node shifts every fixed port. Aggregated: four replicas. Disaggregated: worker-0
is the prefill worker; workers 1-3 decode. All other engine flags are identical.

    python tracks/nvidia-dynamo/sites/nebius-h200-2x8/nemotron-3-nano/render_tp4.py   # writes lab/as-measured/40-workers-tp4*.yaml
"""
import copy
from pathlib import Path

import yaml

SITE = Path(__file__).resolve().parent / 'lab/as-measured'
OUT = {'40-workers-tp4.yaml': 'workers-tp4-aggregated', '40-workers-tp4-disaggregated.yaml': 'workers-tp4-disaggregated'}
NODES = ['<NODE_A_HOSTNAME>', '<NODE_B_HOSTNAME>']
CONTEXT = 262144
MAX_RUNNING = 136  # Per worker; headroom over the 128 average so router imbalance never queues. 140 x 139K tokens fit the KV pool.
ITL_BUCKETS = [round(0.001 * i, 3) for i in range(1, 41)] + [
    0.045, 0.05, 0.06, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0]
# worker index -> (node, port offset). worker-0/1 keep the TP8 ports.
LAYOUT = {0: (0, 0), 1: (1, 0), 2: (0, 1), 3: (1, 1)}


def set_flag(args, flag, value):
    if flag in args:
        args[args.index(flag) + 1] = value
    else:
        args += [flag, value]


def drop_flag(args, flag, has_value=True):
    if flag in args:
        i = args.index(flag)
        del args[i:i + 1 + has_value]


def worker(template, index, role):
    node, offset = LAYOUT[index]
    doc = copy.deepcopy(template)
    name = f'worker-{index}'
    doc['metadata']['name'] = name
    doc['metadata']['labels']['serving-role'] = role
    doc['spec']['selector']['matchLabels']['app'] = name
    labels = doc['spec']['template']['metadata']['labels']
    labels.update(app=name, **{'serving-role': role})
    pod = doc['spec']['template']['spec']
    pod['nodeSelector']['kubernetes.io/hostname'] = NODES[node]
    pod['volumes'][0]['persistentVolumeClaim']['claimName'] = f'model-{node}'
    c = pod['containers'][0]
    args = c['command']
    set_flag(args, '--tensor-parallel-size', '4')
    set_flag(args, '--context-length', str(CONTEXT))
    set_flag(args, '--max-running-requests', str(MAX_RUNNING))
    set_flag(args, '--cuda-graph-max-bs-decode', str(MAX_RUNNING))
    set_flag(args, '--port', str(30000 + 100 * offset))
    set_flag(args, '--kv-events-config',
             '{"publisher":"zmq","topic":"kv-events","endpoint":"tcp://*:%d"}' % (5571 + offset))
    # Let SGLang size the KV pool from memory; the TP8 1M-token cap is too small.
    drop_flag(args, '--max-total-tokens')
    drop_flag(args, '--bucket-inter-token-latency', has_value=False)
    args += ['--bucket-inter-token-latency', *map(str, ITL_BUCKETS)]
    if role in ('prefill', 'decode'):
        args += ['--disaggregation-mode', role, '--disaggregation-transfer-backend', 'nixl',
                 '--disaggregation-bootstrap-port', str(8998 + offset)]
    if role == 'prefill':
        args += ['--disable-cuda-graph']
    for env in c['env']:
        if env['name'] == 'DYN_SYSTEM_PORT':
            env['value'] = str(8081 + offset)
    for probe in ('startupProbe', 'readinessProbe'):
        c[probe]['httpGet']['port'] = 8081 + offset
    for key in ('requests', 'limits'):
        c['resources'][key]['nvidia.com/gpu'] = '4'
    c['resources']['requests'].update(cpu='28', memory='96Gi')
    c['resources']['limits']['memory'] = '384Gi'
    pod['volumes'][1]['emptyDir']['sizeLimit'] = '96Gi'
    return doc


def main():
    template = list(yaml.safe_load_all((SITE / 'workers-tp8-aggregated/40-workers.yaml').read_text()))[0]
    for path, roles in [('40-workers-tp4.yaml', ['aggregated'] * 4),
                        ('40-workers-tp4-disaggregated.yaml', ['prefill', 'decode', 'decode', 'decode'])]:
        docs = [worker(template, i, role) for i, role in enumerate(roles)]
        (SITE / OUT[path] / path).write_text(yaml.safe_dump_all(docs, sort_keys=False))
        print('wrote', path)


if __name__ == '__main__':
    main()
