#!/usr/bin/env python3
"""Extract served CRD schemas from a pinned Dynamo checkout into reference/upstream/.

    git clone --depth 1 --branch v1.4.0 https://github.com/ai-dynamo/dynamo.git /tmp/dynamo-v1.4.0
    python tools/vendor_crds.py /tmp/dynamo-v1.4.0

Only the openAPIV3Schema of each listed version is kept (gzipped JSON), with the
source file's SHA256, so offline validation stays reproducible and small.
"""
import gzip
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reference/upstream/dynamo-v1.4.0'
CRDS = {  # CRD file -> versions to vendor
    'nvidia.com_dynamographdeployments.yaml': ['v1beta1', 'v1alpha1'],
    'nvidia.com_dynamographdeploymentrequests.yaml': ['v1beta1'],
}


def main(checkout):
    bases = Path(checkout) / 'tracks/nvidia-dynamo/install/config/crd/bases'
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for name, versions in CRDS.items():
        raw = (bases / name).read_bytes()
        crd = yaml.safe_load(raw)
        kind = crd['spec']['names']['kind']
        for v in crd['spec']['versions']:
            if v['name'] in versions:
                target = OUT / f'{kind.lower()}_{v["name"]}.schema.json.gz'
                target.write_bytes(gzip.compress(json.dumps(v['schema']['openAPIV3Schema'], sort_keys=True).encode(), mtime=0))
                index[f'{crd["spec"]["group"]}/{v["name"]}/{kind}'] = {
                    'file': target.name, 'source': f'tracks/nvidia-dynamo/install/config/crd/bases/{name}',
                    'source_sha256': hashlib.sha256(raw).hexdigest(), 'served': v.get('served'),
                    'storage': v.get('storage'), 'deprecated': v.get('deprecated', False)}
    (OUT / 'index.json').write_text(json.dumps(index, indent=2, sort_keys=True) + '\n')
    print(json.dumps(index, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
