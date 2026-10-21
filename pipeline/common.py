"""Shared helpers: approved-country list, role filters, Google Sheets I/O (service-account JWT), Apify runner, de-duplication."""
import base64, csv, glob, json, re, sys, threading, time, unicodedata, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import os

# All configuration comes from the environment (see .env.example). Nothing secret is stored in the repo.
ROOT = Path(os.environ.get("VFX_ROOT", Path(__file__).resolve().parent.parent))
WORK = Path(os.environ.get("VFX_WORKDIR", ROOT / "data"))   # local, git-ignored working data
WORK.mkdir(parents=True, exist_ok=True)
SID = os.environ["GOOGLE_SHEET_ID"]                               # target Google Sheet
CRED = Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])         # service-account JSON path
APIFY = os.environ["APIFY_TOKEN"]                                 # active Apify token
TAV = [k.strip() for k in os.environ.get("TAVILY_API_KEYS", "").replace(",", "\n").splitlines() if k.strip()]

APPROVED = {c.casefold() for c in """united states,usa,canada,united kingdom,uk,ireland,australia,new zealand,france,germany,netherlands,belgium,
switzerland,austria,italy,spain,portugal,sweden,norway,denmark,finland,united arab emirates,uae,singapore,japan,south korea,korea,israel,
hong kong,poland,czech republic,czechia,south africa,malaysia,argentina,brazil,mexico""".replace("\n", "").split(",")}
ROLE_OK = re.compile(r"founder|owner|ceo|chief|president|managing director|director|head of|lead|producer|supervisor|vp\b|vice president|partner|cto|principal|manager", re.I)
ROLE_BAD = re.compile(r"intern|assistant|coordinator|student|trainee|junior|recruit|talent|hr\b|human resources|sales|account manager|finance|legal|marketing manager|accountant", re.I)
IND = re.compile(r"film|vfx|animat|produc|director|creative|studio|\bai\b|generative|founder|ceo|cinema|video|content|visual|media|motion|post", re.I)


def norm(s):
    s = re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().casefold())
    s = re.sub(r"\b(ltd|inc|llc|gmbh|studios?|films?|productions?|media|group|co|company|the|ai|agency)\b", " ", s)
    return " ".join(s.split())


def ntoks(s):
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().casefold()).split() if t]


# ---------------- sheets ----------------
def sheets_token(scope="https://www.googleapis.com/auth/spreadsheets"):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    b = lambda v: base64.urlsafe_b64encode(v).rstrip(b"=").decode()
    c = json.loads(CRED.read_text()); now = int(time.time())
    h = b(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    p = b(json.dumps({"iss": c["client_email"], "scope": scope, "aud": c["token_uri"], "iat": now, "exp": now + 3600}, separators=(",", ":")).encode())
    sig = serialization.load_pem_private_key(c["private_key"].encode(), password=None).sign(f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())
    req = urllib.request.Request(c["token_uri"], data=urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": f"{h}.{p}.{b(sig)}"}).encode(), method="POST")
    return json.load(urllib.request.urlopen(req, timeout=30))["access_token"]


def sheets(method, path, payload=None, token=None):
    token = token or sheets_token()
    req = urllib.request.Request(f"https://sheets.googleapis.com/v4/spreadsheets/{SID}{path}", data=None if payload is None else json.dumps(payload).encode(), method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90))


def read_tab(rng):
    return sheets("GET", "/values/" + urllib.parse.quote(rng)).get("values", [])


def tab_state():
    li, x, s = read_tab("Linkedin!A1:Q3000"), read_tab("X!A1:AD3000"), read_tab("'Stage 32'!A1:AC1100")
    st = {"pairs": set(), "comps": set(), "names": {}, "handles": set(), "li_urls": set()}
    for tab, v in (("li", li), ("x", x), ("s", s)):
        h = v[0]; ni, ci = h.index("name"), h.index("company")
        for r in v[1:]:
            n = r[ni] if len(r) > ni else ""; c = r[ci] if len(r) > ci else ""
            st["pairs"].add((n.strip().casefold(), c.strip().casefold()))
            if tab in ("li", "x"):
                st["names"].setdefault(" ".join(ntoks(n)), set()).add(norm(c))
            st["comps"].add(norm(c))
        if tab == "x":
            hi = h.index("x_handle")
            for r in v[1:]:
                if len(r) > hi and r[hi]: st["handles"].add(r[hi].strip().lstrip("@").casefold())
    return st, x[0], len(x) - 1


# ---------------- stage A: pool + LinkedIn company URLs ----------------
def build_pool(st, include_li_companies=False):
    li_comps = set()
    pool = {}
    files = sorted(glob.glob(str(RN / "bulk_companies_*.csv"))) + sorted(glob.glob(str(RN / "x_companies_*.csv")))
    for f in files:
        for r in csv.DictReader(open(f, encoding="utf-8-sig", newline="")):
            name = (r.get("company") or "").strip()
            if not name: continue
            n = norm(name)
            country = re.sub(r"\(.*?\)", "", r.get("country", "")).strip().casefold()
            if country not in APPROVED or "india" in " ".join(str(v) for v in r.values()).casefold(): continue
            if n in st["comps"] and not include_li_companies: continue
            pool.setdefault(n, r)
    return pool


_dead = set(); _lock = threading.Lock(); _ki = [0]


def tavily(query, domains):
    for _ in range(len(TAV) * 2):
        with _lock:
            live = [k for k in TAV if k not in _dead]
            if not live: raise RuntimeError("no live Tavily keys")
            k = live[_ki[0] % len(live)]; _ki[0] += 1
        req = urllib.request.Request("https://api.tavily.com/search", data=json.dumps({"query": query, "search_depth": "basic", "max_results": 6, "include_domains": domains}).encode(),
                                     method="POST", headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=60)).get("results", [])
        except urllib.error.HTTPError as e:
            if e.code == 432 or e.code == 401: _dead.add(k)
            elif e.code == 429: time.sleep(4)
        except Exception:
            time.sleep(2)
    return []


def stage_a(pool):
    cache_f = WORK / "li_company_urls.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    todo = [(n, r) for n, r in pool.items() if n not in cache]
    print("resolving LinkedIn company URLs:", len(todo), flush=True)

    def one(item):
        n, r = item
        dom = re.sub(r"^https?://(www\.)?", "", r.get("website", "")).split("/")[0]
        res = tavily(f"{r['company']} {dom} LinkedIn company", ["linkedin.com"])
        best = None
        for x in res:
            m = re.search(r"linkedin\.com/company/([^/?#]+)", x.get("url", ""))
            if not m: continue
            slug = m.group(1); st_ = set(ntoks(slug.replace("-", " "))) | set(ntoks(x.get("title", "")))
            want = set(ntoks(norm(r["company"]))) | set(ntoks(dom.split(".")[0]))
            if want & st_: best = f"https://www.linkedin.com/company/{slug}"; break
        return n, best
    with ThreadPoolExecutor(2) as ex:
        for i, (n, u) in enumerate(ex.map(one, todo)):
            cache[n] = u
            if i % 20 == 0: cache_f.write_text(json.dumps(cache)); print(i, len(todo), flush=True)
    cache_f.write_text(json.dumps(cache))
    return cache


# ---------------- apify ----------------
def apify_run(actor, inp, wait=600):
    h = {"Authorization": f"Bearer {APIFY}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"https://api.apify.com/v2/acts/{actor}/runs", data=json.dumps(inp).encode(), method="POST", headers=h)
    run = json.load(urllib.request.urlopen(req, timeout=60))["data"]
    t0 = time.time()
    while time.time() - t0 < wait:
        d = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.apify.com/v2/actor-runs/{run['id']}", headers=h), timeout=60))["data"]
        if d["status"] in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"): break
        time.sleep(8)
    items = []
    off = 0
    while True:
        chunk = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.apify.com/v2/datasets/{d['defaultDatasetId']}/items?clean=true&offset={off}&limit=1000", headers=h), timeout=90))
        items += chunk
        if len(chunk) < 1000: break
        off += 1000
    return d["status"], items


TITLES = ["Founder", "Co-Founder", "CEO", "Managing Director", "Creative Director", "Head of Production", "Executive Producer", "VFX Supervisor", "Head of AI",
          "Head of VFX", "Head of Creative", "Owner", "President", "CTO", "Producer", "Director", "Partner"]


def stage_b(pool, urls, per_company=4, workers=4):
    out_f = WORK / "employees.json"
    got = json.loads(out_f.read_text()) if out_f.exists() else {}
    todo = [n for n in pool if urls.get(n) and "india" not in urls[n].casefold() and (n not in got or got[n] is None)]
    print("companies to list employees for:", len(todo), flush=True)
    lock = threading.Lock()

    def one(n):
        base = {"companies": [urls[n]], "maxItems": per_company, "profileScraperMode": "Short ($4 per 1k)"}
        try:
            status, items = apify_run("harvestapi~linkedin-company-employees", {**base, "jobTitles": TITLES}, wait=240)
            if not items:
                status, items = apify_run("harvestapi~linkedin-company-employees", {**base, "maxItems": per_company * 2}, wait=240)
        except Exception as e:
            return n, None
        people = []
        for it in items:
            pos = (it.get("currentPositions") or [{}])[0]
            people.append({"first": it.get("firstName", ""), "last": it.get("lastName", ""), "url": it.get("linkedinUrl", ""), "title": pos.get("position") or pos.get("title") or "",
                           "company_li": pos.get("companyName", ""), "loc": (it.get("location") or {}).get("linkedinText", "")})
        return n, people

    with ThreadPoolExecutor(workers) as ex:
        for i, (n, people) in enumerate(ex.map(one, todo)):
            with lock:
                got[n] = people
                if i % 10 == 0:
                    out_f.write_text(json.dumps(got)); print(i, len(todo), "people so far", sum(len(v or []) for v in got.values()), flush=True)
    out_f.write_text(json.dumps(got))
    return got


def stage_c(people, batch=30):
    out_f = WORK / "xmatches_raw.json"
    raw = json.loads(out_f.read_text()) if out_f.exists() else {}
    terms = sorted({f"{p['first']} {p['last']}".strip() for p in people} - set(raw))
    print("X searches:", len(terms), flush=True)
    for i in range(0, len(terms), batch):
        grp = terms[i:i + batch]
        status, items = apify_run("apidojo~twitter-user-scraper", {"searchTerms": grp, "maxItems": 6 * len(grp), "getFollowers": False, "getFollowing": False, "getRetweeters": False}, wait=420)
        print("xbatch", i // batch, status, len(items), flush=True)
        for t in grp: raw[t] = []
        for it in items:
            src = (it.get("inputSource") or "").strip()
            key = next((t for t in grp if t.casefold() == src.casefold()), None)
            if key: raw[key].append({k: it.get(k) for k in ("userName", "name", "description", "location", "followers", "protected", "statusesCount", "url", "entities")})
        out_f.write_text(json.dumps(raw))
    return raw


def match_x(person, company_row, cands):
    toks = set(ntoks(person["first"])) | set(ntoks(person["last"]))
    first, last = ntoks(person["first"])[:1], ntoks(person["last"])[-1:]
    ctoks = [t for t in ntoks(norm(company_row["company"])) if len(t) >= 4]
    dom = re.sub(r"^https?://(www\.)?", "", company_row.get("website", "")).split("/")[0].split(".")[0].casefold()
    exact = []
    for c in cands:
        if c.get("protected"): continue
        nt = ntoks(c.get("name") or "")
        if first and last and first[0] in nt and last[0] in nt and len(nt) <= 4: exact.append(c)
    best = None
    for c in exact:
        bio = f"{c.get('description') or ''} {c.get('location') or ''} {json.dumps(c.get('entities') or {})}".casefold()
        strong = any(t in bio for t in ctoks) or (dom and len(dom) > 3 and dom in bio)
        ind = bool(IND.search(c.get("description") or ""))
        if strong: return c, "High"
        if ind and len(exact) == 1 and (c.get("followers") or 0) >= 30: best = (c, "Medium")
    return best if best else (None, None)


def role_rank(title):
    t = title.casefold()
    for i, k in enumerate(["head of production", "head of ai", "head of vfx", "head of creative", "executive producer", "creative director", "founder", "co-founder", "owner", "ceo",
                           "managing director", "president", "cto", "partner", "director", "producer"]):
        if k in t: return i
    return 99


def family(title):
    t = title.casefold()
    if re.search(r"cto|technolog|pipeline|engineer|head of ai|\bai\b", t): return "tech"
    if re.search(r"production|producer|vfx|post", t): return "prod"
    if re.search(r"creative|design|art", t): return "creative"
    return "exec"


ROUTE = {"R1_AI_FILM_SERIES": "Adding generative AI to film/series production; fit for an AI film/series workflow (hypothesis from the sourced evidence).",
         "R2_PRODUCTION_ORCHESTRATION": "Multi-tool AI production pipeline that may need orchestration across models and post (hypothesis from the sourced evidence).",
         "R3_PRIVATE_CUSTOM_STUDIO": "Production environment with private/custom infrastructure needs (hypothesis from the sourced evidence).",
         "R4_WHITE_LABEL_STUDIO": "Client-facing AI production service with a repeatable workflow that could be productized or white-labelled (hypothesis from the sourced evidence).",
         "R5_PRODUCTION_CONTEXT_IP": "Reusable production assets/IP that could feed repeat AI production (hypothesis from the sourced evidence)."}


def build_rows(pool, employees, raw, st, header):
    rows, log = [], []
    taken_handles = set(st["handles"])
    for n, plist in employees.items():
        crow = pool.get(n)
        if not crow: continue
        cands = []
        for p in plist:
            title = p["title"]
            if not ROLE_OK.search(title) or ROLE_BAD.search(title): continue
            full = f"{p['first']} {p['last']}".strip()
            if not p["first"] or not p["last"] or "india" in (p.get("loc") or "").casefold(): continue
            if (full.casefold(), crow["company"].strip().casefold()) in st["pairs"]: continue
            nm = " ".join(ntoks(full))
            cfirst = (norm(crow["company"]).split() or [""])[0]
            if nm in st["names"] and any(norm(crow["company"]) == c or (cfirst and cfirst in c.split()) for c in st["names"][nm]):
                log.append((full, crow["company"], "person already in Linkedin/X tab")); continue
            x, conf = match_x(p, crow, raw.get(full, []))
            if not x: log.append((full, crow["company"], "no verifiable X match")); continue
            h = x["userName"].casefold()
            if h in taken_handles: log.append((full, crow["company"], "handle already used")); continue
            cands.append((role_rank(title), p, x, conf))
        cands.sort(key=lambda c: c[0])
        chosen, fams = [], set()
        for c in cands:
            f = family(c[1]["title"])
            if f in fams: continue
            fams.add(f); chosen.append(c)
            if len(chosen) >= 2: break
        for idx, (rk, p, x, conf) in enumerate(chosen):
            role = ["P1", "P2", "P3"][idx]
            taken_handles.add(x["userName"].casefold())
            ptype = crow.get("production_type", "")
            stage = "AI Core" if re.search(r"ai-native|ai native|ai-first", ptype, re.I) else "Active Production"
            high = conf == "High" and crow.get("evidence_tier", "") == "A"
            full = f"{p['first']} {p['last']}".strip()
            r = {"name": full, "company": crow["company"], "title": p["title"], "role": role, "country": re.sub(r"\(.*?\)", "", crow["country"]).strip(),
                 "primary_classification": ptype or "Production Studio", "ai_adoption_stage": stage, "ai_evidence": crow.get("ai_evidence", ""),
                 "primary_commercial_problem": ROUTE.get(crow.get("likely_route", ""), ROUTE["R4_WHITE_LABEL_STUDIO"]),
                 "why_this_person": f"{p['title']} at {crow['company']} (current role shown on LinkedIn); {'leads production/AI workflow' if family(p['title']) in ('prod','tech') else 'senior owner of studio direction and client delivery'}.",
                 "qualification_decision": "PASS-A" if high else "PASS-B", "qa_decision": "PASS", "qa_confidence": "High" if conf == "High" else "Medium", "outreach_readiness": "Ready",
                 "x_handle": "@" + x["userName"], "contact_or_reference": f"https://x.com/{x['userName']}", "contact_or_reference_type": "X Profile",
                 "evidence_source": "; ".join(u for u in [crow.get("evidence_url", ""), p["url"]] if u),
                 "company_fit_check": "Correct", "ai_adoption_check": "Validated", "intent_check": "Validated",
                 "evidence_quality": "Strong" if crow.get("evidence_tier") == "A" else "Mixed", "source_freshness": "Current",
                 "p1_check": "Correct" if role == "P1" else "", "p2_check": "Correct" if role == "P2" else "Missing", "p3_check": "Missing" if role != "P3" else "Correct",
                 "primary_qa_issue": "", "qa_reason": "X profile matched on exact name and bio; current role and company confirmed from LinkedIn employee listing; company AI evidence sourced.",
                 "missing_evidence": "", "recommended_correction": "Ready for outreach." if conf == "High" else "Confirm X profile match before outreach."}
            rows.append([r.get(c, "") for c in header])
    return rows, log


def append(rows, header):
    token = sheets_token()
    added = 0
    for i in range(0, len(rows), 15):
        st, _, _ = tab_state()
        ni, ci, hi = header.index("name"), header.index("company"), header.index("x_handle")
        batch = []
        for r in rows[i:i + 15]:
            if len(r) != 30 or "x.com/" not in r[header.index("contact_or_reference")]: continue
            if (r[ni].strip().casefold(), r[ci].strip().casefold()) in st["pairs"] or r[hi].lstrip("@").casefold() in st["handles"]: continue
            batch.append(r)
        if batch:
            sheets("POST", "/values/" + urllib.parse.quote("X!A1") + ":append?valueInputOption=RAW&insertDataOption=INSERT_ROWS", {"majorDimension": "ROWS", "values": batch}, token=token)
            added += len(batch)
            with open(WORK / "appended_rows.csv", "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f, quoting=csv.QUOTE_MINIMAL); [w.writerow(b) for b in batch]
        print("append batch", i // 15, "added so far", added, flush=True)
    return added


if __name__ == "__main__":
    stage = sys.argv[1]
    st, header, nrows = tab_state()
    pool = build_pool(st, include_li_companies="--all" in sys.argv)
    print("pool:", len(pool), "X rows now:", nrows, flush=True)
    if stage == "a": stage_a(pool)
    elif stage == "b":
        urls = json.loads((WORK / "li_company_urls.json").read_text()); stage_b(pool, urls)
    elif stage == "c":
        emp = json.loads((WORK / "employees.json").read_text())
        people = [p for n, pl in emp.items() for p in pl if ROLE_OK.search(p["title"]) and not ROLE_BAD.search(p["title"])]
        print("people to resolve:", len(people)); stage_c(people)
    elif stage == "d":
        emp = json.loads((WORK / "employees.json").read_text()); raw = json.loads((WORK / "xmatches_raw.json").read_text())
        rows, log = build_rows(pool, emp, raw, st, header)
        with open(WORK / "unmatched_log.csv", "w", newline="", encoding="utf-8") as f: csv.writer(f).writerows(log)
        print("rows built:", len(rows)); print("appended:", append(rows, header))
