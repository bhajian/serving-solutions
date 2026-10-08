#!/usr/bin/env python3
"""Render the production overlays for operator-managed Dynamo graphs.

    python tools/render_production.py    # writes tracks/nvidia-dynamo/production/

For each (model, site) it writes:
  <model>-<site>/namespace/       Namespace (Pod Security labels), default-deny NetworkPolicies,
                                  weights PVC + staging Job, HTTPRoute, auth and rate-limit policies
  <model>-<site>/<topology>/      kustomization: base graph + site JSON patches (RDMA resource,
                                  node placement, UCX devices, KAI queue) [+ Planner for disaggregated]
and once, cluster-wide:
  gateway/                        GatewayClass, Gateway (TLS on 443), cert-manager Certificate

Site values that differ per cluster stay as <PLACEHOLDER> tokens; tools/render_site.py fills
them from platform/site.env. Field names are verified against Dynamo 1.4.0, Gateway API v1.3.0,
Envoy Gateway v1.4.2 and cert-manager v1.17.2 by tools/validate.py (strict).
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.render_graphs import PROFILES, SGLANG_IMAGE  # noqa: E402

OUT = ROOT / 'tracks/nvidia-dynamo/production'
PLANNER_IMAGE = ('nvcr.io/nvidia/ai-dynamo/dynamo-planner:1.4.0'
                 '@sha256:67d4341b038c1fb3e63e0a6b614d0de0f4316a5596378001127d0d07dddf2455')
GRAPH_LABEL = 'nvidia.com/dynamo-graph-deployment-name'
COMPONENT_LABEL = 'nvidia.com/dynamo-component-type'

SITES = {
    'h200': {
        'gpu_product': 'NVIDIA-H200',
        # Network Operator RDMA shared device plugin (operators/network-operator-values.yaml).
        'rdma_resource': 'rdma/rdma_shared_device_a',
        'ucx_net_devices': 'mlx5_0:1,mlx5_1:1,mlx5_2:1,mlx5_3:1,mlx5_4:1,mlx5_5:1,mlx5_6:1,mlx5_7:1',
        'kai_queue': 'inference',
        'weights_size': {'nemotron-3-nano': '200Gi', 'deepseek-v4-pro': '1600Gi'},
    },
}

# Example SLO for the Planner (design guidance, not a measured result). The 1.4.0 Planner
# compares MEAN TTFT/ITL from Prometheus histograms (planner/monitoring/traffic_metrics.py
# L208), not p99, so p99 objectives are translated into tighter mean targets here.
PLANNER_SLO = {
    'nemotron-3-nano': {'p99_ttft_ms': 2000, 'p99_itl_ms': 40, 'mean_ttft_ms': 1000, 'mean_itl_ms': 25},
    'deepseek-v4-pro': {'p99_ttft_ms': 30000, 'p99_itl_ms': 60, 'mean_ttft_ms': 15000, 'mean_itl_ms': 40},
}


def dump(path, docs, header=''):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = header + '\n---\n'.join(yaml.safe_dump(d, sort_keys=False, width=110) for d in docs)
    path.write_text(text)


def kustomization(resources=(), components=(), namespace=None, patches=(), extra=None):
    k = {'apiVersion': 'kustomize.config.k8s.io/v1beta1', 'kind': 'Kustomization'}
    if namespace:
        k['namespace'] = namespace
    k['resources'] = list(resources)
    if components:
        k['components'] = list(components)
    if patches:
        k['patches'] = list(patches)
    if extra:
        k.update(extra)
    return k


def planner_config(model, p):
    slo = PLANNER_SLO[model]
    return {
        'environment': 'kubernetes', 'backend': 'sglang', 'mode': 'disagg', 'optimization_target': 'sla',
        'ttft_ms': slo['mean_ttft_ms'], 'itl_ms': slo['mean_itl_ms'],
        'enable_throughput_scaling': True, 'enable_load_scaling': False,
        'throughput_adjustment_interval_seconds': 60,
        'max_gpu_budget': 16, 'min_endpoint': 1,
        'prefill_engine_num_gpu': p['gpus_per_worker'], 'decode_engine_num_gpu': p['gpus_per_worker'],
        'profile_results_dir': '/workspace/profiling_results', 'pre_deployment_sweeping_mode': 'none',
        'load_predictor': 'arima', 'throughput_metrics_source': 'frontend', 'model_name': p['model_id'],
    }


def planner_component(model, p):
    return {
        'name': 'Planner', 'type': 'planner', 'replicas': 1,
        'podTemplate': {'spec': {
            'containers': [{
                'name': 'main', 'image': PLANNER_IMAGE, 'command': ['python3', '-m', 'dynamo.planner'],
                'args': ['--config', '/workspace/planner_config/planner_config.json'],
                'resources': {'requests': {'cpu': '1', 'memory': '2Gi'}, 'limits': {'memory': '8Gi'}},
                'volumeMounts': [
                    {'name': 'planner-config', 'mountPath': '/workspace/planner_config', 'readOnly': True},
                    {'name': 'profile', 'mountPath': '/workspace/profiling_results', 'readOnly': True}],
            }],
            'volumes': [
                {'name': 'planner-config', 'configMap': {'name': f'{model}-planner-config'}},
                # Written by the profiling DynamoGraphDeploymentRequest (profiling/dgdr.yaml):
                # the operator mounts this PVC as `profiling-output` at /data in the profiling
                # Job (dynamographdeploymentrequest_controller.go L1490, L1579-1595), and the
                # Planner reads selected_{prefill,decode}_interpolation/raw_data.npz from it.
                {'name': 'profile', 'persistentVolumeClaim': {'claimName': f'{model}-planner-profiling', 'readOnly': True}}],
        }},
    }


def site_patches(model, topology, site):
    """JSON patch ops on the base graph's component list (indices fixed by render_graphs)."""
    workers = [1] if topology == 'aggregated' else [1, 2]
    ops = [{'op': 'add', 'path': '/metadata/annotations/nvidia.com~1kai-scheduler-queue', 'value': site['kai_queue']},
           # Operator-coordinated rollout through Grove (consts.go L45-48: RollingRecreate | OnDelete).
           {'op': 'add', 'path': '/metadata/annotations/nvidia.com~1grove-update-strategy', 'value': 'RollingRecreate'}]
    for i in workers:
        base = f'/spec/components/{i}/podTemplate/spec'
        ops += [
            {'op': 'add', 'path': f'{base}/nodeSelector', 'value': {'nvidia.com/gpu.product': site['gpu_product']}},
            {'op': 'add', 'path': f'{base}/containers/0/resources/requests/{site["rdma_resource"].replace("/", "~1")}', 'value': '1'},
            {'op': 'add', 'path': f'{base}/containers/0/resources/limits/{site["rdma_resource"].replace("/", "~1")}', 'value': '1'},
            {'op': 'add', 'path': f'{base}/containers/0/env/-', 'value': {'name': 'UCX_NET_DEVICES', 'value': site['ucx_net_devices']}},
        ]
    return ops


def namespace_bundle(model, p, site_name, site):
    ns = model
    graph = {'matchLabels': {GRAPH_LABEL: model}}
    docs = [
        {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': ns, 'labels': {
            # IPC_LOCK for RDMA is outside the baseline profile, so enforcement is
            # privileged; warn/audit at baseline flag anything beyond that capability.
            'pod-security.kubernetes.io/enforce': 'privileged',
            'pod-security.kubernetes.io/warn': 'baseline',
            'pod-security.kubernetes.io/audit': 'baseline',
            'serving-solutions/expose': 'true'}}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'default-deny', 'namespace': ns},
         'spec': {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress']}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'allow-dns', 'namespace': ns},
         'spec': {'podSelector': {}, 'policyTypes': ['Egress'], 'egress': [{
             'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
                     'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}],
             'ports': [{'protocol': 'UDP', 'port': 53}, {'protocol': 'TCP', 'port': 53}]}]}},
        # Frontend <-> workers <-> planner: Dynamo's TCP request plane and ZMQ event plane
        # use OS-assigned ports, and NIXL/UCX open TCP side channels, so serving pods of
        # one graph may reach each other on any port. RDMA traffic itself bypasses
        # NetworkPolicy (InfiniBand verbs do not traverse the pod network).
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'allow-intra-graph', 'namespace': ns},
         'spec': {'podSelector': graph, 'policyTypes': ['Ingress', 'Egress'],
                  'ingress': [{'from': [{'podSelector': graph}]}], 'egress': [{'to': [{'podSelector': graph}]}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'allow-gateway-to-frontend', 'namespace': ns},
         'spec': {'podSelector': {'matchLabels': {GRAPH_LABEL: model, COMPONENT_LABEL: 'frontend'}},
                  'policyTypes': ['Ingress'], 'ingress': [{
                      'from': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'envoy-gateway-system'}}}],
                      'ports': [{'protocol': 'TCP', 'port': 8000}]}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'allow-prometheus-scrape', 'namespace': ns},
         'spec': {'podSelector': graph, 'policyTypes': ['Ingress'], 'ingress': [{
             'from': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'monitoring'}}}],
             'ports': [{'protocol': 'TCP', 'port': port} for port in (8000, 9090, 9085)]}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'allow-planner-egress', 'namespace': ns},
         'spec': {'podSelector': {'matchLabels': {GRAPH_LABEL: model, COMPONENT_LABEL: 'planner'}},
                  'policyTypes': ['Egress'], 'egress': [
                      {'to': [{'ipBlock': {'cidr': '<API_SERVER_CIDR>'}}], 'ports': [{'protocol': 'TCP', 'port': 443},
                                                                                     {'protocol': 'TCP', 'port': 6443}]},
                      {'to': [{'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'monitoring'}}}],
                       'ports': [{'protocol': 'TCP', 'port': 9090}]}]}},
        # In-cluster benchmark client (tracks/nvidia-dynamo/studies/planned/common): requests to the frontend and
        # metric snapshots from the workers' system port.
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'allow-benchmark-client', 'namespace': ns},
         'spec': {'podSelector': graph, 'policyTypes': ['Ingress'], 'ingress': [{
             'from': [{'podSelector': {'matchLabels': {'serving-solutions/role': 'benchmark-client'}}}],
             'ports': [{'protocol': 'TCP', 'port': 8000}, {'protocol': 'TCP', 'port': 9090}]}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'benchmark-client-egress', 'namespace': ns},
         'spec': {'podSelector': {'matchLabels': {'serving-solutions/role': 'benchmark-client'}},
                  'policyTypes': ['Egress'], 'egress': [{'to': [{'podSelector': graph}],
                                                        'ports': [{'protocol': 'TCP', 'port': 8000}, {'protocol': 'TCP', 'port': 9090}]}]}},
        {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
         'metadata': {'name': 'allow-weights-staging-egress', 'namespace': ns},
         'spec': {'podSelector': {'matchLabels': {'serving-solutions/role': 'weights-staging'}},
                  'policyTypes': ['Egress'], 'egress': [{'ports': [{'protocol': 'TCP', 'port': 443}]}]}},
        {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim', 'metadata': {'name': 'model-weights', 'namespace': ns},
         'spec': {'accessModes': ['ReadWriteMany'], 'storageClassName': '<RWX_STORAGE_CLASS>',
                  'resources': {'requests': {'storage': site['weights_size'][model]}}}},
        staging_job(model, p),
        {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim', 'metadata': {'name': f'{model}-planner-profiling', 'namespace': ns},
         'spec': {'accessModes': ['ReadWriteOnce'], 'resources': {'requests': {'storage': '10Gi'}}}},
    ]
    return docs


def profiling_request(model, p, site):
    slo = PLANNER_SLO[model]
    cache = {'pvcName': 'model-weights', 'pvcMountPath': '/model'}
    if p['weights_subpath']:
        cache['pvcModelPath'] = p['weights_subpath']
    return {
        'apiVersion': 'nvidia.com/v1beta1', 'kind': 'DynamoGraphDeploymentRequest',
        'metadata': {'name': f'{model}-profile', 'namespace': model},
        'spec': {
            'model': p['model_id'], 'backend': 'sglang', 'image': PLANNER_IMAGE,
            # thorough: writes raw interpolation data the Planner reads. rapid instead relies on
            # aiconfigurator models; support for this model on SGLang is TODO(verify-upstream).
            'searchStrategy': 'thorough', 'autoApply': False,
            'hardware': {'gpuSku': 'h200_sxm', 'numGpusPerNode': 8, 'totalGpus': 16, 'rdma': True, 'interconnect': 'nvlink'},
            'workload': {'isl': 8000, 'osl': 1024},
            'sla': {'ttft': slo['p99_ttft_ms'], 'itl': slo['p99_itl_ms']},
            'modelCache': cache,
            'overrides': {'profilingJob': {'template': {'spec': {'containers': [], 'volumes': [
                {'name': 'profiling-output', 'persistentVolumeClaim': {'claimName': f'{model}-planner-profiling'}}]}}}},
        },
    }


def staging_job(model, p):
    from tools.render_graphs import deepseek_revision
    revision = p['revision'] or deepseek_revision()
    sub = p['weights_subpath'] or '.'
    script = (f'set -euo pipefail; dest=/model/{sub}; mkdir -p "$dest"; '
              f'huggingface-cli download {p["model_id"]} --revision {revision} --local-dir "$dest"; '
              'cd "$dest" && find . -type f ! -name SHA256SUMS ! -name DEPLOYED_REVISION ! -path "./.cache/*" '
              '-print0 | sort -z | xargs -0 sha256sum > SHA256SUMS; '
              f'echo {revision} > DEPLOYED_REVISION')
    return {
        'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': 'stage-weights', 'namespace': model},
        'spec': {'backoffLimit': 2, 'template': {
            'metadata': {'labels': {'serving-solutions/role': 'weights-staging'}},
            'spec': {'restartPolicy': 'OnFailure', 'containers': [{
                'name': 'stage', 'image': SGLANG_IMAGE, 'command': ['bash', '-c', script],
                'env': [{'name': 'HF_TOKEN', 'valueFrom': {'secretKeyRef': {'name': 'hf-token', 'key': 'HF_TOKEN'}}},
                        {'name': 'HF_HUB_ENABLE_HF_TRANSFER', 'value': '1'}],
                'resources': {'requests': {'cpu': '8', 'memory': '16Gi'}, 'limits': {'memory': '32Gi'}},
                'volumeMounts': [{'name': 'model-weights', 'mountPath': '/model'}]}],
                'volumes': [{'name': 'model-weights', 'persistentVolumeClaim': {'claimName': 'model-weights'}}]}}},
    }


def edge_bundle(model):
    ns = model
    route = {'apiVersion': 'gateway.networking.k8s.io/v1', 'kind': 'HTTPRoute',
             'metadata': {'name': model, 'namespace': ns},
             'spec': {'parentRefs': [{'name': 'inference', 'namespace': 'envoy-gateway-system', 'sectionName': 'https'}],
                      'hostnames': [f'{model}.<INFERENCE_DOMAIN>'],
                      'rules': [{'matches': [{'path': {'type': 'PathPrefix', 'value': '/v1'}}],
                                 # Operator-created frontend Service: <graph>-<component> (graph.go L744).
                                 'backendRefs': [{'name': f'{model}-frontend', 'port': 8000}],
                                 'timeouts': {'request': '3600s'}}]}}
    target = [{'group': 'gateway.networking.k8s.io', 'kind': 'HTTPRoute', 'name': model}]
    jwt = {'apiVersion': 'gateway.envoyproxy.io/v1alpha1', 'kind': 'SecurityPolicy',
           'metadata': {'name': f'{model}-auth', 'namespace': ns},
           'spec': {'targetRefs': target, 'jwt': {'providers': [{
               'name': 'oidc', 'issuer': '<OIDC_ISSUER_URL>', 'audiences': ['<OIDC_AUDIENCE>'],
               'remoteJWKS': {'uri': '<OIDC_JWKS_URL>'},
               # Tenant comes from a verified token claim, so clients cannot spoof it.
               'claimToHeaders': [{'claim': 'tenant', 'header': 'x-tenant-id'}]}]}}}
    ratelimit = {'apiVersion': 'gateway.envoyproxy.io/v1alpha1', 'kind': 'BackendTrafficPolicy',
                 'metadata': {'name': f'{model}-rate-limit', 'namespace': ns},
                 'spec': {'targetRefs': target, 'rateLimit': {'type': 'Local', 'local': {'rules': [
                     {'clientSelectors': [{'headers': [{'name': 'x-tenant-id', 'type': 'Exact', 'value': 'tenant-a'}]}],
                      'limit': {'requests': 600, 'unit': 'Minute'}},
                     {'clientSelectors': [{'headers': [{'name': 'x-tenant-id', 'type': 'Exact', 'value': 'tenant-b'}]}],
                      'limit': {'requests': 120, 'unit': 'Minute'}},
                     {'limit': {'requests': 60, 'unit': 'Minute'}}]}}}}
    apikey = {'apiVersion': 'gateway.envoyproxy.io/v1alpha1', 'kind': 'SecurityPolicy',
              'metadata': {'name': f'{model}-auth', 'namespace': ns},
              'spec': {'targetRefs': target, 'apiKeyAuth': {
                  'credentialRefs': [{'group': '', 'kind': 'Secret', 'name': f'{model}-api-keys'}],
                  'extractFrom': [{'headers': ['x-api-key']}]}}}
    return route, jwt, ratelimit, apikey


def gateway_bundle():
    return [
        {'apiVersion': 'gateway.networking.k8s.io/v1', 'kind': 'GatewayClass', 'metadata': {'name': 'envoy'},
         'spec': {'controllerName': 'gateway.envoyproxy.io/gatewayclass-controller'}},
        {'apiVersion': 'cert-manager.io/v1', 'kind': 'Certificate',
         'metadata': {'name': 'inference-tls', 'namespace': 'envoy-gateway-system'},
         'spec': {'secretName': 'inference-tls', 'dnsNames': ['*.<INFERENCE_DOMAIN>'],
                  'issuerRef': {'kind': 'ClusterIssuer', 'name': '<TLS_CLUSTER_ISSUER>'}}},
        {'apiVersion': 'gateway.networking.k8s.io/v1', 'kind': 'Gateway',
         'metadata': {'name': 'inference', 'namespace': 'envoy-gateway-system'},
         'spec': {'gatewayClassName': 'envoy', 'listeners': [{
             'name': 'https', 'protocol': 'HTTPS', 'port': 443, 'hostname': '*.<INFERENCE_DOMAIN>',
             'tls': {'mode': 'Terminate', 'certificateRefs': [{'kind': 'Secret', 'name': 'inference-tls'}]},
             # Only namespaces labelled for exposure may attach routes.
             'allowedRoutes': {'namespaces': {'from': 'Selector', 'selector': {
                 'matchLabels': {'serving-solutions/expose': 'true'}}}}}]}},
    ]


HEADER = '# Generated by tools/render_production.py — edit the generator, not this file.\n'


def no_prefix_reuse_component():
    # Aggregated graphs only (worker = component 1). For workloads without prefix reuse,
    # skip radix-tree inserts: in the 8K/128K study each aggregated worker froze ~37 s
    # while 128 finished ~139K-token sequences were inserted at once. Disaggregated decode
    # workers already run without a radix cache in SGLang PD mode and did not stall.
    return {'apiVersion': 'kustomize.config.k8s.io/v1alpha1', 'kind': 'Component',
            'patches': [{'target': {'group': 'nvidia.com', 'version': 'v1beta1', 'kind': 'DynamoGraphDeployment'},
                         'patch': yaml.safe_dump([{'op': 'add', 'path': '/spec/components/1/podTemplate/spec/containers/0/args/-',
                                                   'value': '--disable-radix-cache'}], sort_keys=False)}]}


def blue_green(model, site_name, site):
    """Green graph next to the live (blue) one, traffic split by HTTPRoute weights."""
    green = f'{model}-green'
    ops = site_patches(model, 'aggregated', site) + [{'op': 'replace', 'path': '/metadata/name', 'value': green}]
    green_k = kustomization([f'../../../../graphs/{model}/aggregated'], namespace=model, patches=[
        {'target': {'group': 'nvidia.com', 'version': 'v1beta1', 'kind': 'DynamoGraphDeployment', 'name': model},
         'patch': yaml.safe_dump(ops, sort_keys=False)},
        # The probe and GC-hook ConfigMaps come with the blue graph; both graphs share them.
        *({'patch': yaml.safe_dump({'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': cm, 'namespace': model},
                                    '$patch': 'delete'})} for cm in ('dynamo-frontend-probe', 'dynamo-python-hooks'))])
    route = [{'op': 'replace', 'path': '/spec/rules/0/backendRefs', 'value': [
        {'name': f'{model}-frontend', 'port': 8000, 'weight': 90},
        {'name': f'{green}-frontend', 'port': 8000, 'weight': 10}]}]
    top = kustomization([f'../../{model}-{site_name}/aggregated', 'green'], patches=[
        {'target': {'group': 'gateway.networking.k8s.io', 'version': 'v1', 'kind': 'HTTPRoute', 'name': model},
         'patch': yaml.safe_dump(route, sort_keys=False)}])
    return top, green_k


def main():
    dump(OUT / 'gateway/gateway.yaml', gateway_bundle(), HEADER)
    dump(OUT / 'gateway/kustomization.yaml', [kustomization(['gateway.yaml'])], HEADER)
    dump(OUT / 'components/no-prefix-reuse/kustomization.yaml', [no_prefix_reuse_component()], HEADER)
    top, green = blue_green('nemotron-3-nano', 'h200', SITES['h200'])
    dump(OUT / 'examples/blue-green-nemotron-3-nano/kustomization.yaml', [top], HEADER +
         '# Blue/green model upgrade: render the new revision as the green graph, shift weight, then\n'
         '# promote by renaming. The operator rolls each graph; the gateway moves traffic between them.\n')
    dump(OUT / 'examples/blue-green-nemotron-3-nano/green/kustomization.yaml', [green], HEADER)
    for site_name, site in SITES.items():
        for model, p in PROFILES.items():
            top = OUT / f'{model}-{site_name}'
            route, jwt, ratelimit, apikey = edge_bundle(model)
            dump(top / 'namespace/namespace.yaml', namespace_bundle(model, p, site_name, site), HEADER)
            dump(top / 'namespace/edge.yaml', [route, jwt, ratelimit], HEADER)
            # Validated alternative to OIDC/JWT; swap edge.yaml's SecurityPolicy for this one.
            dump(top / 'namespace/auth-api-key.alternative.yaml', [apikey], HEADER +
                 '# Alternative to the JWT SecurityPolicy in edge.yaml: static API keys in a Secret.\n')
            dump(top / 'namespace/kustomization.yaml', [kustomization(['namespace.yaml', 'edge.yaml'])], HEADER)
            dump(top / 'profiling/dgdr.yaml', [profiling_request(model, p, site)], HEADER +
                 '# SLA profiling for the Planner. Apply once, after the weights are staged; see\n'
                 '# tracks/nvidia-dynamo/studies/planned/03-planner-demo. autoApply is false: the hand-maintained graph stays authoritative.\n')
            dump(top / 'profiling/kustomization.yaml', [kustomization(['dgdr.yaml'], namespace=model)], HEADER)
            for topology in ('aggregated', 'disaggregated'):
                d = top / topology
                patches = [{'target': {'group': 'nvidia.com', 'version': 'v1beta1', 'kind': 'DynamoGraphDeployment',
                                       'name': model},
                            'patch': yaml.safe_dump(site_patches(model, topology, site), sort_keys=False)}]
                extra = None
                if topology == 'disaggregated':
                    patches.append({'target': {'group': 'nvidia.com', 'version': 'v1beta1',
                                               'kind': 'DynamoGraphDeployment', 'name': model},
                                    'patch': yaml.safe_dump([{'op': 'add', 'path': '/spec/components/-',
                                                              'value': planner_component(model, p)}], sort_keys=False)})
                    (d / 'planner_config.json').parent.mkdir(parents=True, exist_ok=True)
                    (d / 'planner_config.json').write_text(json.dumps(planner_config(model, p), indent=2) + '\n')
                    extra = {'generatorOptions': {'disableNameSuffixHash': True},
                             'configMapGenerator': [{'name': f'{model}-planner-config', 'files': ['planner_config.json']}]}
                dump(d / 'kustomization.yaml', [kustomization(
                    [f'../../../graphs/{model}/{topology}', '../namespace'], namespace=model,
                    patches=patches, extra=extra)], HEADER)
            print('wrote', top)


if __name__ == '__main__':
    main()
