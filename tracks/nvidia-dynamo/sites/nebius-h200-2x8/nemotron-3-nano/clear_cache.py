"""Clear idle SGLang KV caches inside the benchmark pod; never deletes weights."""
import asyncio
import json
import os
import socket
import sys

# Kubernetes namespace of the serving stack. Runs recorded before 2026-10-02 used
# deepseek-v4-pro for both profiles; each profile now has its own namespace.
NAMESPACE = os.environ.get('BENCH_NAMESPACE', 'nemotron-3-nano')
os.environ['ETCD_ENDPOINTS'] = f'http://etcd.{NAMESPACE}.svc.cluster.local:2379'
os.environ['DYN_TCP_RPC_HOST'] = socket.gethostbyname(socket.gethostname())
from dynamo.runtime import DistributedRuntime
from benchmarks.driver_lock import append_evidence


async def main():
    mode = sys.argv[1]
    assert mode in ('aggregated', 'disaggregated')
    # Total worker count: 2 for the TP8 layouts, 4 for the TP4 layouts (one prefill).
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    runtime = DistributedRuntime(asyncio.get_running_loop(), 'etcd', 'tcp', event_plane='zmq')
    roles = [('prefill', 1), ('backend', workers - 1)] if mode == 'disaggregated' else [('backend', workers)]
    try:
        for component, expected in roles:
            client = await runtime.endpoint(f'nemotron-3-nano.{component}.clear_kv_blocks').client()
            await asyncio.wait_for(client.wait_for_instances(), 30)
            await asyncio.sleep(1)
            ids = client.instance_ids()
            assert len(ids) == expected, (component, ids)
            for instance in ids:
                deadline = asyncio.get_running_loop().time() + 240
                while True:
                    responses = [r async for r in await client.direct({}, instance, annotated=False)]
                    assert len(responses) == 1, responses
                    result = responses[0]
                    entry = {'component': component, 'instance': instance, 'response': result,
                             'run_label': os.environ.get('BENCH_RUN_LABEL', ''), 'namespace': NAMESPACE}
                    append_evidence('study-records', entry)
                    print(json.dumps(entry), flush=True)
                    if result['status'] == 'success':
                        break
                    if ('requests are active' not in result.get('message', '')
                            or asyncio.get_running_loop().time() >= deadline):
                        raise RuntimeError(result)
                    await asyncio.sleep(5)
    finally:
        runtime.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
