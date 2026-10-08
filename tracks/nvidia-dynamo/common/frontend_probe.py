#!/usr/bin/env python3
"""Readiness/liveness for the Dynamo frontend that checks discovered workers.

Dynamo 1.4.0's frontend /health returns 200 even with zero registered workers and
after the prefill router deactivates (lib/llm/src/http/service/health.rs L63-98), so
Kubernetes cannot see a frontend that lost discovery. This probe reads the same
/health JSON and requires at least one `generate` instance for every component in
PROBE_REQUIRE (default "backend"; "backend,prefill" for disaggregated graphs).

  frontend_probe.py ready   exit 0 when every required component has an instance
  frontend_probe.py live    exit 1 only after workers were seen and then missing for
                            longer than PROBE_LOSS_GRACE_S (default 300), so a cold
                            start that waits for workers is never restarted
"""
import json
import os
import sys
import time
import urllib.request

URL = os.environ.get('PROBE_URL', 'http://127.0.0.1:8000/health')
REQUIRE = [c for c in os.environ.get('PROBE_REQUIRE', 'backend').split(',') if c]
GRACE = float(os.environ.get('PROBE_LOSS_GRACE_S', '300'))
STATE = os.environ.get('PROBE_STATE_DIR', '/tmp')


def missing_components():
    with urllib.request.urlopen(URL, timeout=3) as r:
        body = json.load(r)
    present = {i.get('component') for i in body.get('instances', []) if i.get('endpoint') == 'generate'}
    return [c for c in REQUIRE if c not in present]


def main(mode):
    seen, lost = os.path.join(STATE, 'workers-seen'), os.path.join(STATE, 'workers-lost-since')
    try:
        missing = missing_components()
    except Exception as exc:  # frontend not answering: let the HTTP liveness default decide
        print(f'probe: /health unavailable: {exc}')
        return 1 if mode == 'ready' else 0
    if not missing:
        open(seen, 'w').close()
        if os.path.exists(lost):
            os.remove(lost)
        return 0
    print(f'probe: no discovered instances for {missing}')
    if mode == 'ready':
        return 1
    if not os.path.exists(seen):
        return 0  # cold start: workers have not registered yet
    if not os.path.exists(lost):
        with open(lost, 'w') as f:
            f.write(str(time.time()))
        return 0
    return 1 if time.time() - float(open(lost).read() or 0) > GRACE else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'ready'))
