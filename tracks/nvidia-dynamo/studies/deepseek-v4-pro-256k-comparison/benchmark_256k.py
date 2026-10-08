"""Run one complete 256K cohort after verifying both idle caches were cleared."""
import os
import datetime,json,pathlib,subprocess,sys,time
# Kubernetes namespace of the serving stack. Runs recorded before 2026-10-02 used
# deepseek-v4-pro for both profiles; each profile now has its own namespace.
NAMESPACE = os.environ.get('BENCH_NAMESPACE', 'deepseek-v4-pro')
# Node IPs come from the site env (see platform/site.env.example); never hard-code them.
NODE_IPS = {k: os.environ.get(k) or sys.exit(f'Set {k} (see platform/site.env.example)') for k in ('NODE_A_IP', 'NODE_B_IP')}
mode=sys.argv[1]
assert mode in ('aggregated','disaggregated')
logdir=pathlib.Path('study-records');logdir.mkdir(exist_ok=True)
# One driver per results directory: a second one would flush caches under a live run.
from benchmarks.driver_lock import DriverBusy, acquire, now  # noqa: E402
try:
    LOCK = acquire(logdir)
except DriverBusy as exc:
    sys.exit(str(exc))
start=time.time()
record={'mode':mode,'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sessions':8,'concurrency':4,'input_tokens':256000,'output_budget':256,'cache_protocol':'flush both workers before run; allow within-session prefix reuse','client':'benchmark-client pod on node 0; Kubernetes ClusterIP'}
code=1
try:
 with (logdir/f'{mode}-cache-clear.log').open('a') as f:
  f.write(f'# cache clear {now()}\n'); f.flush()
  subprocess.run([sys.executable, 'clear_cache.py',mode],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=540, env={**os.environ, 'BENCH_RUN_LABEL': mode})
 command=[sys.executable,'-u','-m','benchmarks.run','--base-url',f'http://frontend.{NAMESPACE}.svc.cluster.local:8000/v1','--model','deepseek-ai/DeepSeek-V4-Pro-0813','--technology','dynamo-'+('agg' if mode=='aggregated' else 'disagg')+'-k8s','--deployment',mode+'-deployment.json','--dataset','dataset.jsonl','--sessions','8','--max-model-len','262144','--min-input-tokens','250001','--output-tokens','256','--concurrency','4','--warmup','1','--cache-state','mixed','--metrics-url',f"http://{NODE_IPS['NODE_A_IP']}:8081/metrics",'--metrics-url',f"http://{NODE_IPS['NODE_B_IP']}:8081/metrics",'--results','results']
 record['command']=command
 (logdir/f'{mode}-started.json').write_text(json.dumps(record,indent=2)+'\n')
 with (logdir/f'{mode}-benchmark.log').open('w') as f:
  code=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT).returncode
finally:
 record.update(exit_code=code,elapsed_seconds=time.time()-start,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 (logdir/f'{mode}-completed.json').write_text(json.dumps(record,indent=2)+'\n')
sys.exit(code)
