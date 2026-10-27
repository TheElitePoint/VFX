"""Company crawler: visits each company site (home + key subpages) and records country, business type and generative-AI signals.
Resumable: appends one JSON line per domain to xpipe/company_crawl.jsonl."""
import json,re,sys,ssl,glob,os,urllib.request,unicodedata
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from common import WORK,APPROVED
ctx=ssl.create_default_context();ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
OUT=WORK/os.environ.get('CRAWL_OUT','company_crawl.jsonl')
STRONG=re.compile(r"midjourney|runway(?:ml)?\b|\bsora\b|\bveo\b|\bkling\b|stable diffusion|comfy ?ui|firefly|\bflux\b|\bpika\b|luma ai|dream machine|elevenlabs|heygen|synthesia|made with ai|created with ai|ai[- ]generated (?:film|video|ad|advert|commercial|campaign|series|short|music video|visual|content|image)|generative ai (?:film|video|production|studio|content|commercial|campaign|visual|animation|vfx)|ai (?:film|video|commercial|animation|vfx|production) (?:studio|company|director|house)|\bgenai\b|gen[- ]ai|text[- ]to[- ]video|ai (?:director|filmmaker|artist)",re.I)
LOOSE=re.compile(r"generative|\bai\b|artificial intelligence|machine learning|neural|synthetic media",re.I)
SEO=re.compile(r"\bseo\b|search engine|digital marketing|social media marketing|lead generation|web design|web development|ppc\b|performance marketing|growth marketing|content marketing|link building|branding agency|pr agency|public relations|consultancy|consulting|saas|software|platform|app development|chatbot|automation agency|ai agency for|ai consulting|recruit|staffing|course|training|academy|university",re.I)
PROD=re.compile(r"\bfilm|\bvideo|animation|animated|vfx|visual effects|production|\bstudio|motion graphic|commercial|post[- ]production|\bcgi\b|\b3d\b|editing|cinemat|documentary|music video|storytelling|creative studio|content creation",re.I)
PATHS=['','/about','/about-us','/work','/portfolio','/ai','/services','/projects']
def fetch(u):
    try:
        r=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0 (compatible; research-crawler)"})
        with urllib.request.urlopen(r,timeout=10,context=ctx) as resp:
            return resp.read(300000).decode('utf-8','ignore'),resp.geturl()
    except Exception: return '',''
def clean(t):
    t=re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>',' ',t);t=re.sub(r'<[^>]+>',' ',t);return re.sub(r'\s+',' ',t.replace('&quot;','"').replace('&amp;','&'))
def crawl(dom):
    rec={'domain':dom,'reachable':False,'loose':0,'strong':0,'seo':0,'prod':0,'snippet':'','title':'','desc':'','pages':0}
    for i,p in enumerate(PATHS):
        raw,final=fetch('https://'+dom+p)
        if not raw and i==0: raw,final=fetch('http://'+dom)
        if not raw: continue
        rec['reachable']=True;rec['pages']+=1
        if i==0:
            m=re.search(r'(?is)<title[^>]*>(.*?)</title>',raw);rec['title']=clean(m.group(1))[:140] if m else ''
            m=re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',raw);rec['desc']=clean(m.group(1))[:240] if m else ''
        t=clean(raw)
        rec['loose']+=len(LOOSE.findall(t));s=STRONG.findall(t);rec['strong']+=len(s)
        if i<=2: rec['seo']+=len(SEO.findall(t[:3500]));rec['prod']+=len(PROD.findall(t[:6000]))
        if s and not rec['snippet']:
            m=STRONG.search(t);rec['snippet']=t[max(0,m.start()-90):m.end()+90][:220]
    return rec
if __name__=="__main__":
    uni=json.load(open(WORK/os.environ.get('UNIVERSE_FILE','company_universe.json')))
    BL=re.compile(r"(linkedin|youtube|facebook|instagram|twitter|x\.com|wikipedia|variety|deadline|forbes|techcrunch|bbc\.|nytimes|wsj|bloomberg|reuters|imdb|vimeo|medium|substack|google\.|apple\.com|amazon|microsoft|adobe|nvidia|openai|runwayml|synthesia|heygen|elevenlabs|netflix|disney|dentsu|havas|publicis|wpp|omnicom|ogilvy|mccann|accenture|deloitte|pwc|ibm|oracle|salesforce|capgemini|cognizant|infosys|wipro|\.edu|\.gov|universit|college|school|news|times|post\b|daily|magazine|blog|festival|conference)",re.I)
    INDIA=re.compile(r"india",re.I)
    APPR=APPROVED
    todo=[]
    done=set()
    if OUT.exists():
        for l in open(OUT):
            try: done.add(json.loads(l)['domain'])
            except Exception: pass
    for d,v in uni.items():
        if d in done or BL.search(d) or d.endswith('.in') or d.endswith('.pk'): continue
        c=(v.get('country') or '').casefold()
        if c and (c not in APPR or INDIA.search(c)): continue
        todo.append(d)
    print(len(uni),'universe |',len(done),'already crawled |',len(todo),'to crawl',flush=True)
    n=0
    with open(OUT,'a') as fh, ThreadPoolExecutor(int(os.environ.get('CRAWL_THREADS','64'))) as ex:
        futs={ex.submit(crawl,d):d for d in todo}
        for f in as_completed(futs):
            try: rec=f.result()
            except Exception: continue
            fh.write(json.dumps(rec)+'\n');fh.flush();n+=1
            if n%500==0: print('crawled',n,flush=True)
    print('crawl done',n)
