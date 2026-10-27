"""Key health check. Reads APIFY_TOKEN_POOL / TAVILY_API_KEYS from the environment, prints a status table, and writes the usable Apify keys (credit above the threshold) to data/apify_pool.txt, largest balance first.
Usage: python pipeline/check_keys.py [--min 0.8]"""
import json,os,sys,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from common import WORK
MIN=float(sys.argv[sys.argv.index('--min')+1]) if '--min' in sys.argv else 0.8
def split(v): return [k.strip() for k in v.replace(',','\n').split() if k.strip()]
def apify(t):
    try:
        d=json.load(urllib.request.urlopen(urllib.request.Request("https://api.apify.com/v2/users/me/limits",headers={"Authorization":"Bearer "+t}),timeout=25))['data']
        cap=d['limits']['maxMonthlyUsageUsd'];used=d['current']['monthlyUsageUsd']
        return t,round(cap-used,2),cap,d['monthlyUsageCycle']['endAt'][:10]
    except urllib.error.HTTPError as e: return t,None,None,f'HTTP {e.code}'
    except Exception as e: return t,None,None,'error'
def tavily(k):
    try:
        r=urllib.request.Request("https://api.tavily.com/search",data=json.dumps({"query":"test","max_results":1}).encode(),headers={"Authorization":"Bearer "+k,"Content-Type":"application/json"});urllib.request.urlopen(r,timeout=20);return k,'usable'
    except urllib.error.HTTPError as e: return k,('out of credit' if e.code in (429,432) else f'invalid (HTTP {e.code})')
    except Exception: return k,'error'
keys=list(dict.fromkeys(split(os.environ.get('APIFY_TOKEN_POOL',''))))
res=list(ThreadPoolExecutor(8).map(apify,keys))
good=sorted([r for r in res if r[1] is not None and r[1]>MIN],key=lambda r:-r[1])
print(f"APIFY: {len(keys)} keys | usable {len(good)} | total ${sum(r[1] for r in good):.2f}")
for t,l,c,e in sorted(res,key=lambda r:-(r[1] or -1)): print(f"  {t[:14]}...  {'$%.2f of $%s, resets %s'%(l,c,e) if l is not None else 'INVALID ('+str(e)+')'}")
(WORK/'apify_pool.txt').write_text('\n'.join(r[0] for r in good)+'\n')
tk=list(dict.fromkeys(split(os.environ.get('TAVILY_API_KEYS',''))))
if tk:
    tr=list(ThreadPoolExecutor(8).map(tavily,tk));print(f"TAVILY: {len(tk)} keys | usable {sum(1 for _,s in tr if s=='usable')}")
    for k,s in tr: print(f"  {k[:12]}...  {s}")
