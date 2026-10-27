"""Google Maps harvester: AI-worded business searches per city (compass/crawler-google-places). Rotates across the Apify key pool and caches each city to data/maps/."""
import json,sys,urllib.request,os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import common as xp
from common import WORK

def left(t):
    try:
        d=json.load(urllib.request.urlopen(urllib.request.Request("https://api.apify.com/v2/users/me/limits",headers={"Authorization":"Bearer "+t}),timeout=25))['data'];return d['limits']['maxMonthlyUsageUsd']-d['current']['monthlyUsageUsd']
    except Exception: return 0
CITIES=[("London, UK","en"),("Manchester, UK","en"),("Birmingham, UK","en"),("Bristol, UK","en"),("Glasgow, UK","en"),("Edinburgh, UK","en"),("Leeds, UK","en"),("Dublin, Ireland","en"),("Los Angeles, CA, USA","en"),("New York, NY, USA","en"),("San Francisco, CA, USA","en"),("Chicago, IL, USA","en"),("Austin, TX, USA","en"),("Atlanta, GA, USA","en"),("Miami, FL, USA","en"),("Seattle, WA, USA","en"),("Boston, MA, USA","en"),("Denver, CO, USA","en"),("Dallas, TX, USA","en"),("Nashville, TN, USA","en"),("Portland, OR, USA","en"),("San Diego, CA, USA","en"),("Toronto, Canada","en"),("Vancouver, Canada","en"),("Montreal, Canada","fr"),("Sydney, Australia","en"),("Melbourne, Australia","en"),("Brisbane, Australia","en"),("Auckland, New Zealand","en"),("Berlin, Germany","de"),("Munich, Germany","de"),("Hamburg, Germany","de"),("Cologne, Germany","de"),("Frankfurt, Germany","de"),("Vienna, Austria","de"),("Zurich, Switzerland","de"),("Geneva, Switzerland","fr"),("Paris, France","fr"),("Lyon, France","fr"),("Marseille, France","fr"),("Brussels, Belgium","fr"),("Amsterdam, Netherlands","nl"),("Rotterdam, Netherlands","nl"),("Madrid, Spain","es"),("Barcelona, Spain","es"),("Valencia, Spain","es"),("Lisbon, Portugal","pt"),("Porto, Portugal","pt"),("Milan, Italy","it"),("Rome, Italy","it"),("Turin, Italy","it"),("Stockholm, Sweden","sv"),("Gothenburg, Sweden","sv"),("Copenhagen, Denmark","da"),("Oslo, Norway","no"),("Helsinki, Finland","fi"),("Warsaw, Poland","pl"),("Krakow, Poland","pl"),("Prague, Czechia","cs"),("Tel Aviv, Israel","en"),("Dubai, UAE","en"),("Abu Dhabi, UAE","en"),("Singapore","en"),("Kuala Lumpur, Malaysia","en"),("Hong Kong","en"),("Tokyo, Japan","ja"),("Osaka, Japan","ja"),("Seoul, South Korea","ko"),("Johannesburg, South Africa","en"),("Cape Town, South Africa","en"),("Sao Paulo, Brazil","pt"),("Rio de Janeiro, Brazil","pt"),("Mexico City, Mexico","es"),("Guadalajara, Mexico","es"),("Buenos Aires, Argentina","es")]
Q={"en":["AI video production studio","generative AI creative studio","AI animation studio","AI film production company","AI advertising studio"],
 "de":["KI Videoproduktion","KI Filmproduktion","generative KI Studio","AI video production studio"],
 "fr":["production vidéo IA","studio créatif IA générative","AI video production studio"],
 "nl":["AI videoproductie","generatieve AI studio","AI video production studio"],
 "es":["producción audiovisual IA","estudio creativo IA generativa","AI video production studio"],
 "pt":["produtora de vídeo IA","estúdio criativo IA generativa","AI video production studio"],
 "it":["produzione video IA","studio creativo IA generativa","AI video production studio"],
 "sv":["AI videoproduktion","AI video production studio"],"da":["AI videoproduktion","AI video production studio"],"no":["AI videoproduksjon","AI video production studio"],"fi":["tekoäly videotuotanto","AI video production studio"],"pl":["produkcja wideo AI","AI video production studio"],"cs":["produkce videa AI","AI video production studio"],
 "ja":["生成AI 映像制作","AI video production studio"],"ko":["생성형 AI 영상 제작","AI video production studio"]}
os.makedirs(WORK/'maps',exist_ok=True)
for loc,lang in CITIES:
    fn=WORK/'maps'/(loc.split(',')[0].replace(' ','_')+'.json')
    if fn.exists(): continue
    pool=[k.strip() for k in os.environ['APIFY_TOKEN_POOL'].replace(',','\n').split() if k.strip()]
    tok=next((t for t in pool if left(t)>0.7),None)
    if not tok: print('no credit');break
    xp.APIFY=tok
    try: st,items=xp.apify_run('compass~crawler-google-places',{"searchStringsArray":Q[lang],"locationQuery":loc,"maxCrawledPlacesPerSearch":30,"language":"en","scrapeContacts":False,"scrapePlaceDetailPage":False},wait=400)
    except Exception as e: print('err',loc,str(e)[:80]);continue
    json.dump(items,open(fn,'w'));print(loc,st,len(items),flush=True)
print('maps harvest done')
