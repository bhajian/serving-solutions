#!/usr/bin/env python3
"""OPTIONAL power-user tool: render deployment files for any model in configs/models.yaml.

The hand-written files in tracks/nvidia-dynamo/sites/hgx-b300-2x8/01-03 are the reference deployments. Use this
tool when you need the same topology for a different model, context length or
engine, then read the output before applying it (see tools/README.md).
"""
import argparse
import copy
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Executed inside the image before starting either worker. Both roles must
# consume the same recorded checkpoint, and meet the model's engine floor.
WORKER_CHECK = '''import os, sys
from pathlib import Path
from importlib.metadata import version
from packaging.version import Version
revision, backend, minimum, *command = sys.argv[1:]
marker = Path('/model/DEPLOYED_REVISION')
if not marker.exists() or marker.read_text().strip() != revision:
    raise SystemExit('Checkpoint revision mismatch: verify /model/DEPLOYED_REVISION on BOTH nodes')
if Version(version(backend)) < Version(minimum):
    raise SystemExit('This model requires ' + backend + ' >= ' + minimum + '; select a compatible complete runtime image')
os.execvp(command[0], command)
'''


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False))


def engine_args(model, stack, role, ctx, seqs, batch, memory, backend='vllm'):
    if backend == 'sglang':
        sg = model['sglang']
        args = ['--model-path', '/model', '--served-model-name', model['model_id'],
                '--tensor-parallel-size', '8', '--context-length', str(ctx),
                '--max-running-requests', str(seqs), '--chunked-prefill-size', str(batch),
                '--mem-fraction-static', str(memory), '--page-size', str(sg['page_size']),
                '--kv-cache-dtype', sg['kv_cache_dtype'], '--disaggregation-mode', role,
                '--disaggregation-transfer-backend', 'nixl', '--disaggregation-bootstrap-port', '8998',
                '--host', '0.0.0.0', '--port',
                ('30000' if stack == 'dynamo' else ('8000' if role == 'prefill' else '8200')),
                '--enable-metrics', '--disable-piecewise-cuda-graph']
        args += sg.get('engine_args', []) + sg.get(stack + '_args', [])
        if stack == 'dynamo':
            args += ['--kv-events-config', json.dumps({
                'publisher': 'zmq', 'topic': 'kv-events', 'endpoint': 'tcp://*:5571'})]
        return args
    args = ['--model', '/model'] if stack == 'dynamo' else ['/model']
    args += ['--served-model-name', model['model_id'], '--tensor-parallel-size', '8',
             '--max-model-len', str(ctx), '--max-num-seqs', str(seqs),
             '--max-num-batched-tokens', str(batch), '--gpu-memory-utilization', str(memory),
             '--block-size', str(model['block_size']), '--kv-cache-dtype', model['kv_cache_dtype'],
             '--enable-prefix-caching']
    args += model['engine_args'] + model.get(stack + '_args', [])
    kv = {'kv_connector': 'NixlConnector', 'kv_role': 'kv_both'}
    if stack == 'llmd':
        kv['kv_role'] = 'kv_producer' if role == 'prefill' else 'kv_consumer'
        kv['kv_load_failure_policy'] = 'fail'
        args += ['--host', '0.0.0.0', '--port', '8000' if role == 'prefill' else '8200']
    else:
        args += ['--disaggregation-mode', role, '--kv-events-config', json.dumps({
            'publisher': 'zmq', 'topic': 'kv-events', 'endpoint': 'tcp://127.0.0.1:5571',
            'enable_kv_cache_events': True})]
    return args + ['--kv-transfer-config', json.dumps(kv)]


def environment(c, m, stack, ip, backend='vllm'):
    env = {'HF_HOME': '/runtime/hf', 'HF_MODULES_CACHE': '/runtime/hf_modules',
           'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
           'VLLM_CACHE_ROOT': '/runtime/vllm', 'TRITON_CACHE_DIR': '/runtime/triton',
           'XDG_CACHE_HOME': '/runtime/cache', 'TORCH_EXTENSIONS_DIR': '/runtime/torch_extensions',
           'PYTHONHASHSEED': '0', 'VLLM_WORKER_MULTIPROC_METHOD': 'spawn',
           'VLLM_HOST_IP': ip, 'VLLM_NIXL_SIDE_CHANNEL_HOST': ip,
           'VLLM_NIXL_SIDE_CHANNEL_PORT': '5600', 'VLLM_HTTP_TIMEOUT_KEEP_ALIVE': '120',
           'UCX_NET_DEVICES': c['ib_devices'], 'UCX_TLS': 'rc_x,rc,cuda_copy,cuda_ipc',
           'UCX_RNDV_SCHEME': 'get_zcopy', 'UCX_RNDV_THRESH': '0',
           'NCCL_SOCKET_IFNAME': c['interface'], 'GLOO_SOCKET_IFNAME': c['interface'],
           'NCCL_IB_DISABLE': '0', 'NIXL_LOG_LEVEL': 'INFO'}
    if stack == 'dynamo':
        env.update(DYN_NAMESPACE='disagg', DYN_DISCOVERY_BACKEND='etcd',
                   ETCD_ENDPOINTS='http://' + c['node_a']['ip'] + ':2379',
                   DYN_REQUEST_PLANE='tcp', DYN_EVENT_PLANE='zmq', DYN_TCP_RPC_HOST=ip,
                   # DYN_TCP_RESPONSE_STREAM_HOST is deliberately unset: an explicit
                   # value broke the Dynamo 1.4.0 frontend (reference/troubleshooting.md).
                   DYN_EVENT_PLANE_HOST=ip,
                   DYN_SYSTEM_PORT='8081')
    if backend == 'sglang':
        env = {k: v for k, v in env.items() if not k.startswith('VLLM_')}
        env.update(SGLANG_DISAGGREGATION_NIXL_BACKEND='UCX',
                   SGLANG_DISAGGREGATION_NIXL_BACKEND_PARAMS=json.dumps({'ucx_devices': c['ib_devices']}))
        env.update(m['sglang'].get('env', {}))
    else:
        env.update(m['env'])
    return env


def deployment(name, namespace, node, container, host=True, volumes=None, labels=None):
    labels = {'app': name, **(labels or {})}
    spec = {'nodeSelector': {'kubernetes.io/hostname': node},
            'automountServiceAccountToken': False, 'terminationGracePeriodSeconds': 180,
            'containers': [container], 'volumes': volumes or []}
    if host:
        spec.update(hostNetwork=True, dnsPolicy='ClusterFirstWithHostNet')
    return {'apiVersion': 'apps/v1', 'kind': 'Deployment',
            'metadata': {'name': name, 'namespace': namespace},
            'spec': {'replicas': 1, 'strategy': {'type': 'Recreate'},
                     'selector': {'matchLabels': labels},
                     'template': {'metadata': {'labels': labels}, 'spec': spec}}}


def probe(path, port):
    return {'httpGet': {'path': path, 'port': port}, 'timeoutSeconds': 5, 'periodSeconds': 15}


def etcd_command(c):
    return ['/usr/local/bin/etcd', '--name=default', '--data-dir=/etcd-data',
            # Binding the private IP failed on the reference hosts; listen on all
            # interfaces and restrict port 2379 with the firewall instead.
            '--listen-client-urls=http://0.0.0.0:2379',
            '--advertise-client-urls=http://' + c['node_a']['ip'] + ':2379',
            '--listen-peer-urls=http://127.0.0.1:2380',
            '--initial-advertise-peer-urls=http://127.0.0.1:2380',
            '--initial-cluster=default=http://127.0.0.1:2380']


def render(a):
    c = yaml.safe_load(Path(a.cluster).read_text())
    m = copy.deepcopy(yaml.safe_load(Path(a.models).read_text())[a.model])
    if c['gpus_per_node'] != 8:
        raise ValueError('This topology uses TP8 and eight GPUs per worker.')
    if m.get('experimental'):
        print('Experimental model/topology: validate engine flags, P/D transfer and output on your GPUs.')
    ctx = a.max_model_len or m['max_model_len']
    if not 1 <= ctx <= m['context_limit']:
        raise ValueError(f'Context must be in 1..{m["context_limit"]}; no implicit RoPE scaling.')
    if a.model_path:
        m['model_path'] = a.model_path
    if a.revision:
        m['revision'] = a.revision
    if not re.fullmatch(r'[0-9a-f]{40}', m['revision']):
        raise ValueError('Model revision must be an immutable 40-character SHA.')
    stack = 'llmd' if a.target == 'llmd' else 'dynamo'
    backend = a.backend
    profile = m['sglang'] if backend == 'sglang' else m
    image_key = stack + ('_sglang_image' if backend == 'sglang' else '_image')
    image = a.image or profile.get(stack + '_image') or c[image_key]
    if backend == 'sglang':
        print('SGLang P/D profiles are experimental on this TP8/TP8 B300 topology; verify KV transfer before benchmarking.')
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    config = {'model_profile': a.model, 'model': m, 'cluster': c, 'image': image, 'backend': backend,
              'technology': 'dynamo-compose' if a.target == 'compose' else stack + '-k8s',
              'max_model_len': ctx, 'max_num_seqs': a.max_num_seqs,
              'max_num_batched_tokens': a.max_num_batched_tokens,
              'gpu_memory_utilization': a.gpu_memory_utilization}
    (out / 'deployment.json').write_text(json.dumps(config, indent=2) + '\n')
    workers = {}
    for role, nodekey in [('prefill', 'node_a'), ('decode', 'node_b')]:
        node = c[nodekey]
        args = engine_args(m, stack, role, ctx, a.max_num_seqs, a.max_num_batched_tokens, a.gpu_memory_utilization, backend)
        env = environment(c, m, stack, node['ip'], backend)
        cmd = (['python3', '-m', 'dynamo.' + backend] if stack == 'dynamo' else
               (['vllm', 'serve'] if backend == 'vllm' else ['python3', '-m', 'sglang.launch_server']))
        runtime = f'{c["runtime_root"]}/{a.model}/{stack}/{backend}/{role}'
        official_patch_image = profile.get(stack + '_image', '')
        use_patched_floor = image.split('@')[0] == official_patch_image.split('@')[0]
        floor_key = 'min_' + backend
        minimum = profile.get(stack + '_' + floor_key, profile[floor_key]) if use_patched_floor else profile[floor_key]
        checked_cmd = ['python3', '-c', WORKER_CHECK, m['revision'], backend, minimum, *cmd, *args]
        workers[role] = dict(image=image, command=checked_cmd, environment=env,
                             runtime=runtime, node=node)
    frontcmd = ['python3', '-m', 'dynamo.frontend', '--http-host', '0.0.0.0',
                '--http-port', '8000', '--router-mode', 'kv', '--router-kv-events',
                '--kv-cache-block-size', str(profile['page_size'] if backend == 'sglang' else m['block_size'])]
    frontcmd += m.get('frontend_args', [])
    if a.target == 'compose':
        for role, w in workers.items():
            worker = {'image': image, 'entrypoint': w['command'], 'network_mode': 'host',
                      'ipc': 'host', 'user': '0', 'gpus': 'all',
                      'devices': ['/dev/infiniband:/dev/infiniband'], 'cap_add': ['IPC_LOCK'],
                      'ulimits': {'memlock': {'soft': -1, 'hard': -1}, 'stack': 67108864},
                      'environment': w['environment'],
                      'volumes': [m['model_path'] + ':/model:ro', w['runtime'] + ':/runtime'],
                      'logging': {'driver': 'json-file', 'options': {'max-size': '100m', 'max-file': '3'}}}
            services = {role: worker}
            if role == 'prefill':
                services['etcd'] = {'image': 'quay.io/coreos/etcd:v3.5.21', 'network_mode': 'host',
                                    'entrypoint': etcd_command(c), 'restart': 'unless-stopped',
                                    'volumes': ['etcd-data:/etcd-data']}
                fenv = environment(c, m, stack, c['node_a']['ip'], backend)
                fenv.pop('DYN_SYSTEM_PORT', None)
                services['frontend'] = {'image': image, 'network_mode': 'host', 'entrypoint': frontcmd,
                    'environment': fenv, 'volumes': [m['model_path'] + ':/model:ro',
                        f'{c["runtime_root"]}/{a.model}/dynamo/{backend}/frontend:/runtime']}
            obj = {'name': 'disagg', 'services': services}
            if role == 'prefill':
                obj['volumes'] = {'etcd-data': {}}
            dump(out / ('node-a.yaml' if role == 'prefill' else 'node-b.yaml'), obj)
        return
    ns = 'dynamo' if stack == 'dynamo' else 'llm-d'
    resources = []
    def save(name, obj):
        dump(out / name, obj)
        resources.append(name)
    save('namespace.yaml', {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {
        'name': ns, 'labels': {'pod-security.kubernetes.io/enforce': 'privileged'}}})
    for role, w in workers.items():
        volumes = [{'name': 'model', 'hostPath': {'path': m['model_path'], 'type': 'Directory'}},
                   {'name': 'runtime', 'hostPath': {'path': w['runtime'], 'type': 'DirectoryOrCreate'}},
                   {'name': 'shm', 'emptyDir': {'medium': 'Memory', 'sizeLimit': '64Gi'}}]
        mounts = [{'name': 'model', 'mountPath': '/model', 'readOnly': True},
                  {'name': 'runtime', 'mountPath': '/runtime'}, {'name': 'shm', 'mountPath': '/dev/shm'}]
        limits = {'nvidia.com/gpu': '8', 'memory': c['worker_memory_limit']}
        if c['privileged_rdma']:
            volumes.append({'name': 'rdma', 'hostPath': {'path': '/dev/infiniband', 'type': 'Directory'}})
            mounts.append({'name': 'rdma', 'mountPath': '/dev/infiniband'})
        elif c['rdma_resource']:
            limits[c['rdma_resource']] = '1'
        else:
            raise ValueError('Configure either privileged RDMA or an RDMA device-plugin resource.')
        container = {'name': 'modelserver', 'image': image, 'command': w['command'],
            'env': [{'name': k, 'value': str(v)} for k, v in w['environment'].items()],
            'resources': {'requests': {'cpu': '16', 'memory': c['worker_memory_request'],
                                      **{k: v for k, v in limits.items() if k != 'memory'}}, 'limits': limits},
            'securityContext': {'runAsUser': 0, 'privileged': c['privileged_rdma'],
                                'capabilities': {'add': ['IPC_LOCK']}}, 'volumeMounts': mounts}
        if stack == 'llmd':
            port = 8000 if role == 'prefill' else 8200
            container.update(startupProbe={**probe('/health', port), 'failureThreshold': 480},
                             readinessProbe=probe('/health', port))
        else:
            container.update(startupProbe={**probe('/health', 8081), 'failureThreshold': 480},
                             readinessProbe=probe('/health', 8081))
        labels = {'llm-d.ai/role': role, 'llm-d.ai/guide': 'two-node-pd'} if stack == 'llmd' else {}
        dep = deployment(role, ns, w['node']['hostname'], container, volumes=volumes, labels=labels)
        if stack == 'llmd' and role == 'decode':
            dep['spec']['template']['spec']['initContainers'] = [{
                'name': 'routing-proxy', 'image': c['llmd_sidecar_image'], 'restartPolicy': 'Always',
                'args': ['--port=8000', '--model-server-port=8200',
                         '--kv-connector=' + ('sglang' if backend == 'sglang' else 'nixlv2'),
                         '--zap-log-level=1', '--secure-proxy=false'],
                'env': [{'name': 'SGLANG_BOOTSTRAP_PORT', 'value': '8998'}] if backend == 'sglang' else [],
                'ports': [{'name': 'sidecar', 'containerPort': 8000}],
                'resources': {'requests': {'cpu': '1', 'memory': '1Gi'}, 'limits': {'memory': '4Gi'}},
                'securityContext': {'allowPrivilegeEscalation': False, 'runAsNonRoot': True}}]
        save(role + '.yaml', dep)
    if stack == 'dynamo':
        etcd = {'name': 'etcd', 'image': 'quay.io/coreos/etcd:v3.5.21', 'command': etcd_command(c),
                'volumeMounts': [{'name': 'etcd', 'mountPath': '/etcd-data'}]}
        save('etcd.yaml', deployment('etcd', ns, c['node_a']['hostname'], etcd, volumes=[{
            'name': 'etcd', 'hostPath': {'path': '/data/disagg/etcd', 'type': 'DirectoryOrCreate'}}]))
        fenv = environment(c, m, stack, c['node_a']['ip'], backend); fenv.pop('DYN_SYSTEM_PORT', None)
        front = {'name': 'frontend', 'image': image, 'command': frontcmd,
                 'env': [{'name': k, 'value': str(v)} for k, v in fenv.items()],
                 'ports': [{'name': 'http', 'containerPort': 8000}],
                 'readinessProbe': probe('/health', 8000),
                 'volumeMounts': [{'name': 'model', 'mountPath': '/model', 'readOnly': True},
                                  {'name': 'runtime', 'mountPath': '/runtime'}]}
        save('frontend.yaml', deployment('frontend', ns, c['node_a']['hostname'], front, volumes=[
            {'name': 'model', 'hostPath': {'path': m['model_path'], 'type': 'Directory'}},
            {'name': 'runtime', 'emptyDir': {}}]))
        save('service.yaml', {'apiVersion': 'v1', 'kind': 'Service',
            'metadata': {'name': 'frontend', 'namespace': ns},
            'spec': {'selector': {'app': 'frontend'}, 'ports': [{'port': 8000, 'targetPort': 8000}]}})
    else:
        # One worker per role: role filters + least-loaded selection need no
        # borrowed, model-specific peak-prefill-throughput calibration.
        plugins = [{'type': t} for t in ['always-disagg-pd-decider', 'prefill-filter',
                   'decode-filter', 'active-request-scorer', 'max-score-picker']]
        plugins.append({'type': 'disagg-profile-handler', 'parameters': {
            'deciders': {'prefill': 'always-disagg-pd-decider'}}})
        picker = {'apiVersion': 'llm-d.ai/v1alpha1', 'kind': 'EndpointPickerConfig',
                  'plugins': plugins, 'schedulingProfiles': [{'name': r, 'plugins': [
                      {'pluginRef': r + '-filter'}, {'pluginRef': 'active-request-scorer'},
                      {'pluginRef': 'max-score-picker'}]} for r in ['prefill', 'decode']]}
        dump(out / 'router' / 'values.yaml', {'router': {
            'epp': {'replicas': 1, 'pluginsConfigFile': 'pd-config.yaml',
                    'pluginsCustomConfig': {'pd-config.yaml': yaml.safe_dump(picker, sort_keys=False)}},
            'inferencePool': {'failureMode': 'FailClose'},
            'proxy': {'failOpen': False, 'args': ['--service-node', 'envoy-sidecar',
                       '--log-level', 'warn', '--concurrency', '8', '-c', '/etc/envoy/envoy.yaml']},
            'modelServers': {'matchLabels': {'llm-d.ai/guide': 'two-node-pd'}},
            'extraServicePorts': [{'name': 'http', 'port': 80, 'protocol': 'TCP', 'targetPort': 8081}]}})
    dump(out / 'kustomization.yaml', {'apiVersion': 'kustomize.config.k8s.io/v1beta1',
                                    'kind': 'Kustomization', 'resources': resources})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', choices=['compose', 'dynamo', 'llmd'], required=True)
    p.add_argument('--model', default='nemotron-ultra')
    p.add_argument('--backend', choices=['vllm', 'sglang'], default='vllm')
    p.add_argument('--cluster', default=str(ROOT / 'configs/cluster.yaml'))
    p.add_argument('--models', default=str(ROOT / 'configs/models.yaml'))
    p.add_argument('--out', required=True)
    p.add_argument('--image'); p.add_argument('--model-path'); p.add_argument('--revision')
    p.add_argument('--max-model-len', type=int)
    p.add_argument('--max-num-seqs', type=int, default=32)
    p.add_argument('--max-num-batched-tokens', type=int, default=8192)
    p.add_argument('--gpu-memory-utilization', type=float, default=.8)
    a = p.parse_args()
    if a.max_num_seqs < 1 or a.max_num_batched_tokens < 1 or not 0 < a.gpu_memory_utilization < 1:
        p.error('Sequence and batch limits must be positive; memory fraction must be between 0 and 1.')
    try:
        render(a)
    except (ValueError, KeyError) as e:
        p.error(str(e))


if __name__ == '__main__':
    main()
