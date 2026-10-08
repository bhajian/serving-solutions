#!/usr/bin/env python3
"""Validate manifests against pinned upstream schemas (no cluster access).

Checks two things:
1. Every raw YAML object under the scanned roots (Compose files, Kubernetes objects).
2. The rendered output of every kustomization (`kustomize build`), so overlays and
   patches are validated as they would be applied.

Schemas: Kubernetes v1.33 OpenAPI, Compose spec, and CRDs pinned below. Dynamo 1.4.0
CRD schemas are vendored in reference/upstream (tools/vendor_crds.py); the rest are
downloaded once into --cache-dir. An object whose kind has no schema is an error.
"""
import argparse
import gzip
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
import urllib.request

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
VENDORED = ROOT / 'reference/upstream/dynamo-v1.4.0'
DOWNLOADS = {
    'kubernetes.json': 'https://raw.githubusercontent.com/kubernetes/kubernetes/v1.33.0/api/openapi-spec/swagger.json',
    'compose.json': 'https://raw.githubusercontent.com/compose-spec/compose-spec/main/schema/compose-spec.json',
    'inference.yaml': 'https://github.com/kubernetes-sigs/gateway-api-inference-extension/releases/download/v1.5.0/v1-manifests.yaml',
    'gateway-api.yaml': 'https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml',
    'envoy-gateway.yaml': 'https://github.com/envoyproxy/gateway/releases/download/v1.4.2/install.yaml',
    'prometheus-operator.yaml': 'https://github.com/prometheus-operator/prometheus-operator/releases/download/v0.83.0/stripped-down-crds.yaml',
    'cert-manager.yaml': 'https://github.com/cert-manager/cert-manager/releases/download/v1.17.2/cert-manager.crds.yaml',
    'nicclusterpolicy.yaml': 'https://raw.githubusercontent.com/Mellanox/network-operator/v26.7.0/deployment/network-operator/crds/mellanox.com_nicclusterpolicies.yaml',
}
SKIP_FILES = {'kustomization.yaml', 'values.yaml', 'experiment.yaml', 'sweep.yaml'}


class Loader(yaml.SafeLoader):
    """SafeLoader that reads the YAML 1.1 '=' value tag (used in some CRD bundles) as a string."""


Loader.add_constructor('tag:yaml.org,2002:value', lambda loader, node: loader.construct_scalar(node))


def load_all(text):
    return yaml.load_all(text, Loader=Loader)


PLACEHOLDER = re.compile(r'<([A-Z][A-Z0-9_]+)>')


def sample(token):
    """A reserved-range value with the right shape for a <PLACEHOLDER> (RFC 5737, RFC 2606)."""
    if token.endswith('_CIDR'):
        return '192.0.2.0/24'
    if token.endswith('_IP'):
        return '192.0.2.10'
    if token.endswith('_URL'):
        return 'https://idp.example.com/' + token.lower()
    if token.endswith('DOMAIN'):
        return 'example.com'
    return token.lower().replace('_', '-')


def as_rendered(text):
    """Validate manifests as tools/render_site.py would emit them."""
    return PLACEHOLDER.sub(lambda m: sample(m.group(1)), text)


def strict(obj):
    """Reject unknown fields, like kubeconform -strict.

    Kubernetes silently prunes unknown fields from custom resources, so a misspelled
    or misplaced field would pass a plain schema check and then vanish on apply.
    Every object schema that lists properties becomes closed unless it explicitly
    preserves unknown fields or already defines additionalProperties.
    """
    if isinstance(obj, dict):
        if ('properties' in obj and 'additionalProperties' not in obj
                and not obj.get('x-kubernetes-preserve-unknown-fields')):
            obj['additionalProperties'] = False
        for v in obj.values():
            strict(v)
    elif isinstance(obj, list):
        for v in obj:
            strict(v)
    return obj


def normalize(obj):
    # Kubernetes OpenAPI v2 expresses IntOrString as type=string plus a custom
    # format; JSON Schema needs the explicit type union.
    if isinstance(obj, dict):
        if obj.get('format') == 'int-or-string' or obj.get('x-kubernetes-int-or-string'):
            obj['type'] = ['string', 'integer']
            obj.pop('anyOf', None)
        for v in obj.values():
            normalize(v)
    elif isinstance(obj, list):
        for v in obj:
            normalize(v)
    return obj


class Registry:
    def __init__(self, cache):
        cache.mkdir(parents=True, exist_ok=True)
        for name, url in DOWNLOADS.items():
            if not (cache / name).exists():
                (cache / name).write_bytes(urllib.request.urlopen(url, timeout=120).read())
        self.openapi = strict(normalize(json.loads((cache / 'kubernetes.json').read_text())))
        self.compose = json.loads((cache / 'compose.json').read_text())
        self.crds = {}
        for name in ('inference.yaml', 'gateway-api.yaml', 'envoy-gateway.yaml', 'prometheus-operator.yaml',
                     'cert-manager.yaml', 'nicclusterpolicy.yaml'):
            for doc in load_all((cache / name).read_text()):
                if doc and doc.get('kind') == 'CustomResourceDefinition':
                    for v in doc['spec']['versions']:
                        if v.get('served', True) and 'schema' in v:
                            key = (doc['spec']['group'], v['name'], doc['spec']['names']['kind'])
                            self.crds[key] = v['schema']['openAPIV3Schema']
        for key, meta in json.loads((VENDORED / 'index.json').read_text()).items():
            group, version, kind = key.split('/')
            self.crds[(group, version, kind)] = json.loads(gzip.decompress((VENDORED / meta['file']).read_bytes()))

    def schema(self, obj):
        kind, api = obj['kind'], obj['apiVersion']
        group, _, version = api.rpartition('/')
        if (group, version, kind) in self.crds:
            return strict(normalize(json.loads(json.dumps(self.crds[(group, version, kind)]))))
        core = 'core' if not group else group.split('.')[0]
        key = f'io.k8s.api.{core}.{version}.{kind}'
        if group.endswith('.k8s.io') and group.split('.')[0] in ('rbac', 'networking', 'storage', 'scheduling', 'policy'):
            key = f'io.k8s.api.{group.split(".")[0]}.{version}.{kind}'
        if key in self.openapi['definitions']:
            return {'$ref': '#/definitions/' + key, 'definitions': self.openapi['definitions']}
        raise LookupError(f'no schema for {api} {kind}')


def validate_objects(registry, objects, source):
    errors, count = [], 0
    for obj in objects:
        if not obj:
            continue
        try:
            if 'services' in obj and 'kind' not in obj:
                jsonschema.validate(obj, registry.compose)
            else:
                jsonschema.Draft7Validator(registry.schema(obj)).validate(obj)
            count += 1
        except (jsonschema.ValidationError, LookupError, KeyError) as exc:
            name = obj.get('metadata', {}).get('name') if isinstance(obj, dict) else None
            msg = exc.message if isinstance(exc, jsonschema.ValidationError) else str(exc)
            where = '/'.join(map(str, getattr(exc, 'absolute_path', [])))
            errors.append(f'{source}: {obj.get("kind")}/{name}: {msg[:300]} at {where}')
    return count, errors


def is_component(directory):
    k = yaml.safe_load((directory / 'kustomization.yaml').read_text()) or {}
    return k.get('kind') == 'Component'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--root', action='append', help='Folder to scan; repeatable. Default: tracks/ and platform/.')
    p.add_argument('--cache-dir', default=str(ROOT / 'build/schema-cache'))
    a = p.parse_args(argv)
    registry = Registry(Path(a.cache_dir))
    roots = [Path(r) for r in (a.root or [ROOT / 'tracks', ROOT / 'platform'])]
    roots = [r for r in roots if r.exists()]
    raw_count, built_count, errors = 0, 0, []
    for path in sorted(p for r in roots for p in r.rglob('*.yaml')):
        # Patch fragments and Helm values (including llm-d router arm-*.yaml) are not standalone objects; they are
        # validated through `kustomize build` or by Helm.
        if (path.name in SKIP_FILES or path.name.endswith('values.yaml') or path.name.startswith(('patch-', 'values', 'kustomization', 'arm-')) or 'patches' in path.parts
                or 'helm' in path.parts):
            continue
        n, e = validate_objects(registry, yaml.safe_load_all(as_rendered(path.read_text())), path.relative_to(ROOT))
        raw_count += n; errors += e
    if shutil.which('kustomize'):
        for k in sorted(p.parent for r in roots for p in r.rglob('kustomization.yaml')):
            if is_component(k):
                continue
            out = subprocess.run(['kustomize', 'build', str(k)], capture_output=True, text=True)
            if out.returncode:
                errors.append(f'{k.relative_to(ROOT)}: kustomize build failed: {out.stderr.strip()[:400]}')
                continue
            n, e = validate_objects(registry, yaml.safe_load_all(as_rendered(out.stdout)), f'kustomize build {k.relative_to(ROOT)}')
            built_count += n; errors += e
    else:
        errors.append('kustomize not found on PATH; install it to validate overlays')
    for e in errors:
        print('ERROR', e, file=sys.stderr)
    print(f'{raw_count} raw objects and {built_count} rendered kustomize objects passed upstream schema '
          f'validation; {len(errors)} errors. Run a server dry-run for cluster admission checks.')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
