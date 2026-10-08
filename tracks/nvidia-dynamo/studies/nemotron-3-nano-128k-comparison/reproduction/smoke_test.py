#!/usr/bin/env python3
"""Verify model discovery, non-streaming and streaming through the public API."""
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

MODEL = 'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16'


def request(base, body=None):
    path = '/v1/models' if body is None else '/v1/chat/completions'
    return urllib.request.urlopen(urllib.request.Request(
        base.rstrip('/') + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'}), timeout=300)


def completion(base, stream=False):
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content':
        'What is 17 plus 25? Reply with only the number.'}],
        'max_tokens': 64, 'temperature': 0,
        'chat_template_kwargs': {'enable_thinking': False}, 'stream': stream}
    with request(base, body) as response:
        if not stream:
            result = json.load(response)
            text = result['choices'][0]['message']['content']
            assert result['choices'][0]['finish_reason'] == 'stop', result
            assert result['usage']['completion_tokens'] > 0, result
        else:
            text, done = '', False
            for line in response:
                line = line.decode().strip()
                if not line.startswith('data: '):
                    continue
                payload = line[6:]
                if payload == '[DONE]':
                    done = True
                    break
                event = json.loads(payload)
                assert 'error' not in event, event
                for choice in event.get('choices', []):
                    text += choice.get('delta', {}).get('content') or ''
            assert done, 'Stream ended without [DONE]'
    assert text and text.strip().rstrip('.') == '42', repr(text)
    return {'stream': stream, 'answer': text}


def main():
    base = sys.argv[1]
    with request(base) as response:
        models = json.load(response)
    assert MODEL in [x['id'] for x in models['data']], models
    print('Model discovery passed')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda stream: completion(base, stream), [False, True, False, True]))
    print(json.dumps({'status': 'passed', 'endpoint': base, 'requests': results}, indent=2))


if __name__ == '__main__':
    main()
