"""Measure cold 256K prefill throughput on one replica, bypassing the router.

Runs inside the benchmark client pod. Resets the replica's prefix cache, sends the
first turn of one dataset session directly to the replica, and reports TTFT plus the
throughput in both model tokens and the router's estimate units (prompt bytes / 4),
which is what the prefix-cache-affinity filter's peakPrefillThroughput expects.

  python calibrate.py <replica> <session-index>
"""
import json
import sys
import time

import httpx

replica, index = int(sys.argv[1]), int(sys.argv[2])
base = f'http://deepseek-v4-pro-{replica}.deepseek-v4-pro.llm-d.svc.cluster.local:8000'
with open('/bench/datasets/generated/deepseek-v4-pro-chatbot-256k-32.jsonl') as f:
    session = json.loads(f.readlines()[index])
messages = session['turns'][0]['messages']
prompt_bytes = sum(len(m['content'].encode()) for m in messages if isinstance(m.get('content'), str))

assert httpx.post(base + '/reset_prefix_cache', timeout=120).status_code == 200
body = {'model': 'deepseek-ai/DeepSeek-V4-Pro-0813', 'messages': messages, 'max_tokens': 16,
        'temperature': 0, 'stream': True, 'stream_options': {'include_usage': True},
        'chat_template_kwargs': {'thinking': False}}
start = time.perf_counter(); ttft = None; usage = None
with httpx.stream('POST', base + '/v1/chat/completions', json=body, timeout=3600) as r:
    r.raise_for_status()
    for line in r.iter_lines():
        if not line.startswith('data: ') or line == 'data: [DONE]':
            continue
        event = json.loads(line[6:])
        if ttft is None and any((c.get('delta') or {}).get('content') or (c.get('delta') or {}).get('reasoning_content')
                                for c in event.get('choices', [])):
            ttft = time.perf_counter() - start
        usage = event.get('usage') or usage
prompt_tokens = usage['prompt_tokens']
print(json.dumps({
    'replica': replica, 'session': session['id'], 'ttft_s': round(ttft, 2),
    'prompt_tokens': prompt_tokens, 'cached_tokens': (usage.get('prompt_tokens_details') or {}).get('cached_tokens'),
    'prompt_bytes': prompt_bytes,
    'prefill_tokens_per_s': round(prompt_tokens / ttft),
    'router_units_per_s': round(prompt_bytes / 4 / ttft),
}))
