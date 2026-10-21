"""Tavily search wrapper that rotates across a pool of API keys and retires exhausted ones."""
import sys,json,re,csv,time,itertools,threading,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(__import__('pathlib').Path(__file__).parent))
from common import *
import os
keys=[k.strip() for k in os.environ['TAVILY_API_KEYS'].replace(',','\n').split() if k.strip()]
dead=set();lock=threading.Lock();cyc=itertools.cycle(keys)
def tv(q,n=10,depth="basic",domains=None):
    for _ in range(len(keys)*2):
        with lock:
            k=next(cyc)
            if k in dead: continue
        p={"query":q,"max_results":n,"search_depth":depth,"include_answer":False}
        if domains:p["include_domains"]=domains
        try:
            r=urllib.request.Request("https://api.tavily.com/search",data=json.dumps(p).encode(),headers={"Authorization":"Bearer "+k,"Content-Type":"application/json"})
            return json.load(urllib.request.urlopen(r,timeout=60)).get("results",[])
        except urllib.error.HTTPError as e:
            if e.code in(432,401,403): dead.add(k)
            elif e.code==429: time.sleep(3)
        except Exception: time.sleep(2)
    return []
if __name__=="__main__":
    L=read_tab('Linkedin!A1:Q4000');X=read_tab('X!A1:AD3000')
    known={norm(r[1]) for r in L[1:]+X[1:] if len(r)>1}
    for f in __import__('glob').glob('leads_candidates*_20261008.csv'):
        known|={norm(r['company']) for r in csv.DictReader(open(f))}
    qs=[]
    kw=["generative AI production studio","AI-generated commercial agency","AI animation studio client work","AI film production company","AI video production agency brands","AI visual effects studio generative","AI music video production company","AI-powered creative studio campaign","synthetic media production studio","generative AI advertising production"]
    reg=["United States","United Kingdom","Canada","Australia","Germany","France","Netherlands","Spain","Italy","Sweden","Denmark","Singapore","Japan","South Korea","UAE","Brazil","Mexico","Israel","Poland","Ireland","Portugal","Norway","Finland","Belgium","Switzerland","South Africa","Hong Kong","Argentina","New Zealand","Austria"]
    for kwd in kw:
        for rg in reg: qs.append(f"{kwd} {rg}")
    print(len(qs),'queries')
    res={}
    def run(q):
        out=tv(q,10)
        with lock:
            for r in out:
                u=r['url'];res.setdefault(u,{'url':u,'title':r['title'],'content':r['content'][:300],'q':q})
    with ThreadPoolExecutor(3) as ex: list(ex.map(run,qs))
    print(len(res),'urls; dead keys',len(dead))
    json.dump(list(res.values()),open(WORK/'tv_company_urls.json','w'))
