"""Clear idle SGLang KV caches inside the benchmark pod; never deletes weights."""
import asyncio
import json
import os
import socket
import sys

os.environ['ETCD_ENDPOINTS'] = 'http://etcd.deepseek-v4-pro.svc.cluster.local:2379'
os.environ['DYN_TCP_RPC_HOST'] = socket.gethostbyname(socket.gethostname())
from dynamo.runtime import DistributedRuntime


async def main():
    mode = sys.argv[1]
    assert mode in ('aggregated', 'disaggregated')
    runtime = DistributedRuntime(asyncio.get_running_loop(), 'etcd', 'tcp', event_plane='zmq')
    roles = [('prefill', 1), ('backend', 1)] if mode == 'disaggregated' else [('backend', 2)]
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
                    print(json.dumps({'component': component, 'instance': instance, 'response': result}), flush=True)
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
