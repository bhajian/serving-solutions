| Metric | optimized-baseline (c8, b1) | optimized-baseline-tuned (c8, t1) |
| --- | ---: | ---: |
| Requests (failed) | 96 (0) | 96 (0) |
| Wall time (s) | 581.1998443480006 | 563.6776223650013 |
| Output tokens/s | 15.7 | 15.6 |
| TTFT first turn p50 / p90 (s) | 31.04 / 78.43 | 28.08 / 54.21 |
| TTFT follow-up p50 / p90 (s) | 27.57 / 54.21 | 1.07 / 42.06 |
| Follow-ups with ≥ 90% cached | 30/64 | 34/64 |
| Prompt tokens prefilled (M) | 16.9 | 15.88 |
| Requests per replica | 21 / 21 / 31 / 23 | 26 / 24 / 18 / 28 |
| Prefix hit rate per replica | 0.19 / 0.238 / 0.484 / 0.261 | 0.231 / 0.458 / 0.111 / 0.536 |
| Router decisions | load_override 1, no_match 32, sticky 63 | load_override 1, no_match 34, sticky 61 |
