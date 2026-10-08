"""Summarize the 256K routing study from raw/<label>/<run_id>/.

  python analyze.py [raw-dir]

Writes summary.json and summary.md next to this script. Per arm: TTFT by turn, follow-up
cache hits and re-prefilled tokens (from per-request cached_tokens), per-replica requests
and prefix-cache hit rate (vLLM metric deltas), and the router's affinity decisions.
Metric snapshot order follows run_arm.sh: replicas 0..N-1, then the router.
"""
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'raw'
SERIES = re.compile(r'^([a-zA-Z_:][\w:]*)(\{[^}]*\})?\s+([-+\d.eE]+|NaN)$')


def prom(path):
    values = defaultdict(float)
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        m = SERIES.match(line)
        if m and m.group(3) != 'NaN':
            values[(m.group(1), m.group(2) or '')] += float(m.group(3))
    return values


def delta(run, index, name, label_filter=''):
    before, after = prom(run / f'metrics-before-{index}.prom'), prom(run / f'metrics-after-{index}.prom')
    out = defaultdict(float)
    for (n, labels), v in after.items():
        if n == name and label_filter in labels:
            out[labels] += v - before.get((n, labels), 0.0)
    return out


def pct(values, q):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def summarize(label_dir):
    pre = json.loads((label_dir / 'pre-run.json').read_text())
    run = next(p for p in label_dir.iterdir() if p.is_dir())
    rows = list(csv.DictReader((run / 'requests.csv').open()))
    summary = json.loads((run / 'summary.json').read_text()) if (run / 'summary.json').exists() else {}
    metadata = json.loads((run / 'metadata.json').read_text())
    ok = [r for r in rows if r['success'] == 'True']
    for r in ok:
        r['turn'] = int(r['turn']); r['prompt'] = int(r['prompt_tokens']); r['cached'] = int(r['cached_tokens'] or 0)
        r['ttft_s'] = float(r['ttft_ms']) / 1000; r['out'] = int(r['completion_tokens'] or 0)
    first = [r for r in ok if r['turn'] == 0]
    follow = [r for r in ok if r['turn'] > 0]
    hit = [r for r in follow if r['cached'] >= 0.9 * r['prompt']]
    replicas = len([k for k in pre['cache_resets']])
    per_replica = []
    for i in range(replicas):
        req = sum(delta(run, i, 'vllm:request_success_total').values())
        queries = sum(delta(run, i, 'vllm:prefix_cache_queries_total').values())
        hits = sum(delta(run, i, 'vllm:prefix_cache_hits_total').values())
        prompt = sum(delta(run, i, 'vllm:prompt_tokens_total').values())
        per_replica.append({'replica': i, 'requests': round(req), 'prompt_tokens': round(prompt),
                            'prefix_hit_rate': round(hits / queries, 3) if queries else None})
    decisions = {re.search(r'outcome="([^"]+)"', k).group(1): round(v)
                 for k, v in delta(run, replicas, 'llm_d_epp_prefix_cache_affinity_filter_decisions_total').items()
                 if 'outcome=' in k and v}
    def stats(rs):
        t = [r['ttft_s'] for r in rs]
        return {'n': len(rs), 'p50_s': round(pct(t, .5), 2) if t else None, 'p90_s': round(pct(t, .9), 2) if t else None,
                'mean_s': round(statistics.mean(t), 2) if t else None, 'max_s': round(max(t), 2) if t else None}
    prompt_total = sum(r['prompt'] for r in ok)
    cached_total = sum(r['cached'] for r in ok)
    return {
        'label': label_dir.name, 'arm': pre['arm'], 'run_id': run.name,
        'concurrency': int(metadata['concurrency']), 'dataset_sha256': metadata['dataset_sha256'],
        'requests': len(rows), 'failed': len(rows) - len(ok),
        'wall_s': summary.get('wall_time_s') or summary.get('duration_s'),
        'output_tok_s': summary.get('output_throughput_tps'),
        'ttft_first_turn': stats(first), 'ttft_follow_up': stats(follow),
        'follow_up_cache_hits': f'{len(hit)}/{len(follow)}',
        'follow_up_hit_share': round(len(hit) / len(follow), 3) if follow else None,
        'prompt_tokens': prompt_total, 'cached_tokens': cached_total,
        're_prefilled_tokens': prompt_total - cached_total,
        'per_replica': per_replica, 'router_decisions': decisions,
    }


def table(results):
    lines = ['| Metric | ' + ' | '.join(f"{r['arm']} (c{r['concurrency']}, {r['label']})" for r in results) + ' |',
             '| --- |' + ' ---: |' * len(results)]
    def row(name, f):
        lines.append(f'| {name} | ' + ' | '.join(str(f(r)) for r in results) + ' |')
    row('Requests (failed)', lambda r: f"{r['requests']} ({r['failed']})")
    row('Wall time (s)', lambda r: r['wall_s'])
    row('Output tokens/s', lambda r: r['output_tok_s'] and round(r['output_tok_s'], 1))
    row('TTFT first turn p50 / p90 (s)', lambda r: f"{r['ttft_first_turn']['p50_s']} / {r['ttft_first_turn']['p90_s']}")
    row('TTFT follow-up p50 / p90 (s)', lambda r: f"{r['ttft_follow_up']['p50_s']} / {r['ttft_follow_up']['p90_s']}")
    row('Follow-ups with ≥ 90% cached', lambda r: r['follow_up_cache_hits'])
    row('Prompt tokens prefilled (M)', lambda r: round(r['re_prefilled_tokens'] / 1e6, 2))
    row('Requests per replica', lambda r: ' / '.join(str(p['requests']) for p in r['per_replica']))
    row('Prefix hit rate per replica', lambda r: ' / '.join(str(p['prefix_hit_rate']) for p in r['per_replica']))
    row('Router decisions', lambda r: ', '.join(f'{k} {v}' for k, v in sorted(r['router_decisions'].items())) or '—')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    order = {'random': 0, 'optimized-baseline': 1, 'optimized-baseline-tuned': 2}
    results = [summarize(d) for d in RAW.iterdir() if d.is_dir() and (d / 'pre-run.json').exists()]
    results.sort(key=lambda r: (-r['concurrency'], order.get(r['arm'], 9)))
    (HERE / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    (HERE / 'summary.md').write_text(table(results))
    print(table(results))
