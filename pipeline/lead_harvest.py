"""Runs the Apify lead-finder actor with automatic token rotation: skips tokens whose monthly credit is exhausted and caches each run to data/."""
import json,os,sys,time,urllib.request,urllib.error
sys.path.insert(0,str(__import__('pathlib').Path(__file__).parent))
import common as xp
from common import WORK
pool=[t for t in os.environ['APIFY_TOKEN_POOL'].replace(',','\n').split()]
def spent(t):
    d=json.load(urllib.request.urlopen(urllib.request.Request("https://api.apify.com/v2/users/me/limits",headers={"Authorization":"Bearer "+t}),timeout=30))["data"]
    return d['limits']['maxMonthlyUsageUsd']-d['current']['monthlyUsageUsd']
def run(inp,tag,min_left=0.6):
    out=WORK/f'pool_{tag}.json'
    if out.exists(): return json.load(open(out))
    for t in pool:
        try: left=spent(t)
        except Exception: continue
        if left<min_left: continue
        xp.APIFY=t
        try:
            st,items=xp.apify_run("microworlds~leads-finder",inp,wait=800)
        except Exception as e:
            print('err',tag,str(e)[:80]);continue
        print(tag,st,len(items),'token',t[:18],'left before',round(left,2),flush=True)
        if items or st=='SUCCEEDED':
            json.dump(items,open(out,'w'));return items
    print('no token for',tag);return []
