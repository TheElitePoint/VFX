"""Cheap first-pass filter: fetches each company homepage and keeps only sites whose visible text mentions generative-AI use."""
import sys,re,json,csv,glob,collections,urllib.request,ssl
sys.path.insert(0,str(__import__('pathlib').Path(__file__).parent))
from common import *
from concurrent.futures import ThreadPoolExecutor
ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
AI=re.compile(r"generative|gen[\s-]?ai|\bgenai\b|midjourney|runway|sora\b|veo\b|kling|stable diffusion|comfyui|firefly|\bai[\s-](generated|powered|driven|assisted|native|first|film|video|studio|animation|production|content|visual|tools?|workflow|creative)|artificial intelligence|machine learning|neural|text[\s-]to[\s-]video|synthetic media|ai\s+(director|artist|filmmaker)",re.I)
def fetch(u):
    try:
        r=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
        return urllib.request.urlopen(r,timeout=12,context=ctx).read(400000).decode('utf-8','ignore')
    except Exception: return ''
def check(dom):
    txt=fetch('https://'+dom)
    if not txt: txt=fetch('http://'+dom)
    if not txt: return dom,-1,''
    txt=re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>',' ',txt)
    txt=re.sub(r'<[^>]+>',' ',txt);txt=re.sub(r'\s+',' ',txt)
    txt=txt.replace('&quot;','"')
    txt=re.sub(r'"[A-Za-z]+"\s*:\s*\{?[^}]{0,80}generative[^}]{0,80}\}?',' ',txt)
    txt=re.sub(r'(?i)luminous|firefly logo|our logo is a firefly',' ',txt)
    hits=AI.findall(txt)
    m=AI.search(txt);ctxt=txt[max(0,m.start()-80):m.end()+80] if m else ''
    return dom,len(hits),ctxt[:200]
if __name__=="__main__":
    tags=sys.argv[1:]
    items=[]
    for t in tags: items+=json.load(open(WORK/f'pool_{t}.json'))
    L=read_tab('Linkedin!A1:Q4000');X=read_tab('X!A1:AD3000');S=read_tab("'Stage 32'!A1:AC1100")
    names={norm(r[0]) for r in L[1:]+X[1:]+S[1:]}
    known=set(norm(r[1]) for r in L[1:]+X[1:]+S[1:] if len(r)>1)
    for f in glob.glob(str(WORK/'candidates_*.csv'))+glob.glob(str(WORK/'roster_*.csv')):
        for r in csv.DictReader(open(f,encoding='utf-8-sig')): known.add(norm(r.get('company','')))
    for f in glob.glob(str(WORK/'*rejected*.csv')):
        for r in csv.reader(open(f,encoding='utf-8-sig',newline='')):
            if r: known.add(norm(r[0]))
            if len(r)>1: known.add(norm(r[1]))
    NOSALES=re.compile(r"business development|sales|partnership|account (executive|manager|director)|talent|recruit|marketing|finance|legal|\bhr\b|procurement|customer success|intern\b|assistant|student|engineer|developer|designer|editor|artist|animator|coordinator|accountant",re.I)
    INDIA=re.compile(r"\bindia\b|mumbai|delhi|bangalore|bengaluru|hyderabad|chennai|pune|kolkata|gurgaon|noida",re.I)
    by={}
    for it in items:
        f,l=(it.get('first_name') or '').strip(),(it.get('last_name') or '').strip();co=(it.get('organization_name') or '').strip();t=it.get('title') or ''
        d=(it.get('organization_primary_domain') or '').lower().replace('www.','')
        if not f or not l or not co or not d or 'linkedin.com/in/' not in (it.get('linkedin_url') or ''): continue
        if not ROLE_OK.search(t) or ROLE_BAD.search(t) or NOSALES.search(t): continue
        if INDIA.search(' '.join(str(it.get(k) or '') for k in ('city','state','country','headline'))) or d.endswith('.in'): continue
        if ' '.join(ntoks(f+' '+l)) in names or norm(co) in known: continue
        by.setdefault(d,[]).append(it)
    print(len(items),'leads ->',len(by),'new domains',flush=True)
    res=list(ThreadPoolExecutor(24).map(check,list(by)))
    ok={d:(n,c) for d,n,c in res if n>0}
    print('fetched',sum(1 for d,n,c in res if n>=0),'AI-mentioning',len(ok),flush=True)
    def rk(t):
        t=t.lower()
        for i,k in enumerate(['founder','owner','ceo','managing director','president','creative director','head of ai','executive producer','head of production','chief']):
            if k in t: return i
        return 9
    out=[]
    for d,(n,c) in ok.items():
        v=sorted(by[d],key=lambda it:rk(it.get('title') or ''))
        it=v[0]
        out.append({'first':it['first_name'],'last':it['last_name'],'title':it.get('title') or '','company':it.get('organization_name'),'domain':d,'website':it.get('organization_website_url') or '','company_linkedin':it.get('organization_linkedin_url') or '','company_twitter':(it.get('organization_twitter_url') or '').rstrip('/').split('/')[-1],'city':it.get('city') or '','country':it.get('country') or '','linkedin_url':it.get('linkedin_url'),'headline':(it.get('headline') or '')[:160],'group':'pool','x_handle':'','x_bio':'','x_conf':'','ai_hits':n,'ai_snippet':c})
    out.sort(key=lambda o:-o['ai_hits'])
    with open(WORK/'pool_candidates.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=list(out[0].keys()),quoting=csv.QUOTE_MINIMAL);w.writeheader();w.writerows(out)
    print('wrote',len(out),flush=True)
