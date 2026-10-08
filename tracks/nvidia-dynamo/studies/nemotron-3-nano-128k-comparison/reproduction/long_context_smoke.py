from pathlib import Path
import json,time,urllib.request
from transformers import AutoTokenizer
model='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16'
row=json.loads(Path('datasets/generated/nemotron-3-nano-chatbot-128k-32.jsonl').open().readline())
messages=row['turns'][0]['messages']
corpus=messages[0]['content'];offset=corpus.find('\n',len(corpus)//2)
messages[0]['content']=corpus[:offset]+'\nBenchmark verification key: ORBIT-7319.\n'+corpus[offset:]
messages[-1]['content']='Find the benchmark verification key in the reference context. Reply with only its value.'
tokenizer=AutoTokenizer.from_pretrained('build/nemotron-128k/tokenizer')
encoded=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False)
planned=len(encoded['input_ids'] if hasattr(encoded,'keys') else encoded)
assert 128000<=planned<131072-64
body={'model':model,'messages':messages,'max_tokens':64,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
start=time.monotonic()
request=urllib.request.Request('http://<LOADBALANCER_IP>:8000/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=300) as response:result=json.load(response)
answer=result['choices'][0]['message']['content'];passed=answer.strip().rstrip('.')=='ORBIT-7319'
record={'test':'128K context retrieval, marker inserted halfway through corpus','planned_prompt_tokens':planned,'elapsed_s':time.monotonic()-start,'passed':passed,'response':result}
Path('build/nemotron-128k/long-context-smoke.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'passed':passed,'prompt_tokens':result['usage']['prompt_tokens'],'planned':planned,'answer':answer,'elapsed_s':record['elapsed_s']}))
assert result['usage']['prompt_tokens']==planned
assert passed,answer
