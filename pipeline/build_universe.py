"""Builds data/company_universe.json (one entry per company domain) from lead-finder pools (data/pool_*.json) and Google Maps results (data/maps/*.json)."""
import glob,json,sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).parent))
from common import WORK
uni={}
def add(d,**kw):
    d=(d or '').lower().strip().replace('www.','')
    if not d or '.' not in d: return
    e=uni.setdefault(d,{})
    for k,v in kw.items():
        if v and not e.get(k): e[k]=v
for f in glob.glob(str(WORK/'pool_*.json')):
    try: d=json.load(open(f))
    except Exception: continue
    for it in (d if isinstance(d,list) else [x for v in d.values() for x in v]):
        if isinstance(it,dict):
            add(it.get('organization_primary_domain'),company=it.get('organization_name'),website=it.get('organization_website_url'),li=it.get('organization_linkedin_url'),tw=it.get('organization_twitter_url'),country=it.get('country'),city=it.get('city'))
CC={'US':'united states','GB':'united kingdom','CA':'canada','AU':'australia','NZ':'new zealand','IE':'ireland','DE':'germany','AT':'austria','CH':'switzerland','FR':'france','BE':'belgium','NL':'netherlands','ES':'spain','PT':'portugal','IT':'italy','SE':'sweden','NO':'norway','DK':'denmark','FI':'finland','PL':'poland','CZ':'czech republic','IL':'israel','AE':'united arab emirates','SG':'singapore','MY':'malaysia','HK':'hong kong','JP':'japan','KR':'south korea','ZA':'south africa','BR':'brazil','MX':'mexico','AR':'argentina'}
for f in glob.glob(str(WORK/'maps'/'*.json')):
    try: items=json.load(open(f))
    except Exception: continue
    for it in items:
        w=it.get('website') or ''
        h=urlparse(w if w.startswith('http') else 'http://'+w).netloc if w else ''
        add(h,company=it.get('title'),website=w,country=CC.get((it.get('countryCode') or '').upper(),''),city=it.get('city'))
json.dump(uni,open(WORK/'company_universe.json','w'))
print(len(uni),'companies written to',WORK/'company_universe.json')
