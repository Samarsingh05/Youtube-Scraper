import os, re, time, argparse, pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from rapidfuzz import fuzz
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

TRANSCRIPT_FUZZ_RATIO = 78
CONTEXT_WINDOW = 12
REQUEST_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0"
SLEEP_BETWEEN_SEARCHES = 0.35

INTENT_WORDS = [
    "review","tutorial","demo","how to","walkthrough","using","compare","guide","pricing",
    "setup","overview","vs","alternatives","competitors","features","integration","use case",
    "for beginners","tips","productivity","automation","workflow","screen share","screen record",
    "video message","screen capture","chrome extension","desktop recorder"
]

BRANDS = {
    "gamma": {
        "domains": ["gamma.app","gamma.ai"],
        "required_terms": [
            "ai presentation","presentation tool","deck builder","ai slides","create slides",
            "presentation builder","pitch deck","magic slides","generate slides","markdown to slides",
            "docs to slides","ai document to slides"
        ],
        "negatives": [
            "gamma rays","radiation","hulk","marvel","fish","gamma correction","greek letter",
            "astronomy","physics","scientific gamma","warframe","hdr gamma"
        ],
        "brand_aliases": ["gamma"]
    },
    "loom": {
        "domains": ["loom.com"],
        "required_terms": [
            "screen recorder","screen record","record screen","screen capture","video message",
            "async video","camera bubble","share screen","video walkthrough","video messaging",
            "send video message","desktop recorder","chrome extension","meeting recording",
            "loom ai","ai summary","video tool","screen recording software"
        ],
        "negatives": [
            "weaving","loom bands","knitting","knit","crochet","bracelet","rug","yarn","textile",
            "weave","cloth","fabric","sewing","bead loom","card weaving","paper loom","pattern",
            "handmade","threads","needle","toy loom","macrame","craft","cardboard","weaver"
        ],
        "brand_aliases": ["loom"]
    },
    "guidde": {
        "domains": ["guidde.com"],
        "required_terms": [
            "how-to guide","procedure docs","step-by-step","workflow capture","auto doc",
            "process doc","sops","training videos","video documentation","product tours",
            "create guides","record workflow","document process"
        ],
        "negatives": [],
        "brand_aliases": ["guidde"]
    },
    "scribe": {
        "domains": ["scribehow.com","scribehow"],
        "required_terms": [
            "how-to guides","process doc","documentation","workflow","auto generate docs",
            "sops","process recording","step-by-step guide","scribe tutorial","scribe app",
            "record steps","create documentation","auto documentation"
        ],
        "negatives": [
            "journalism","scribe pen","scribe bible","egyptian scribe","scribe media",
            "ancient scribe","medical scribe job"
        ],
        "brand_aliases": ["scribe","scribe how","scribehow"]
    },
    "scribe how": {
        "domains": ["scribehow.com"],
        "required_terms": [
            "how-to guides","process doc","documentation","workflow","sops","scribe tutorial",
            "record steps","create documentation"
        ],
        "negatives": [],
        "brand_aliases": ["scribe how","scribehow"]
    },
    "clueso ai": {
        "domains": ["clueso.ai"],
        "required_terms": [
            "ai support","monitoring","analytics","alerting","observability","ticket deflection",
            "customer support","helpdesk ai","zendesk","intercom","help center",
            "support automation","agent assist","csat","deflection","faq automation","product analytics"
        ],
        "negatives": [
            "music","song","album","lyrics","rapper","concert","tour","singer","hip hop","pop music",
            "pink panther","clouseau","detective movie","french detective","german singer","live"
        ],
        "brand_aliases": ["clueso ai","cluesoai","clueso"]
    },
    "emergent ai": {
        "domains": ["emergent.ai"],
        "required_terms": [
            "ai tool","saas","ai agents","automation","workflow","no-code","productivity",
            "ai assistant","ai automation","startup tool","agentic","product demo","builder",
            "app builder","agent builder","autonomous agent"
        ],
        "negatives": [
            "emergent behavior","emergent properties","complex systems","philosophy","biology",
            "evolution","cognitive science","emergence theory","swarm behavior","theory","paper"
        ],
        "brand_aliases": ["emergent ai","emergentai","emergent"]
    },
    "lovable": {
        "domains": ["lovable.dev","lovable.so"],
        "required_terms": [
            "ai engineer","build apps","coding assistant","ship apps","lovable ai","no-code ai",
            "ai app builder","code generation","ai developer tool","generate app","create app"
        ],
        "negatives": [
            "romantic","love story","dating","couples","valentine","romantic song",
            "relationship","love advice","love poem","love quotes"
        ],
        "brand_aliases": ["lovable"]
    },
    "synthesia": {
        "domains": ["synthesia.io"],
        "required_terms": [
            "ai avatar","talking avatar","ai presenter","text to video","text-to-video",
            "avatar video","studio","video generator","lip sync","lipsync","talking head",
            "elearning","training video","localize video","script to video","avatar presenter",
            "corporate training","enterprise video","brand avatar"
        ],
        "negatives": [
            "piano","keyboard","midi","sheets","sheet music","notes","learn piano","piano tutorial",
            "practice","arpeggio","chords","melody","rhythm game","gameplay","android game","ios game",
            "mobile game","pc game","synthesia piano","synthesia app",
            # Neurology/perception
            "synesthesia","synaesthesia","grapheme color","sensory cross","neuroscience","perception",
            # Music creation software confusion
            "synthesizer","synthesisers","vst","daw","ableton","fl studio","logic pro","kontakt",
            "midi controller","sound design"
        ],
        "brand_aliases": ["synthesia","synthesia ai"]
    }
}

def build_service(api_key):
    return build("youtube","v3",developerKey=api_key)

def youtube_search_paged(svc, q, max_results, order, video_duration):
    out=[]; tok=None
    while True:
        try:
            req=svc.search().list(
                part="id,snippet",
                q=q,
                type="video",
                maxResults=min(max_results,50),
                order=order,
                videoDuration=(video_duration if video_duration!="any" else None),
                pageToken=tok
            )
            res=req.execute()
        except HttpError as e:
            if e.resp.status==403:
                raise SystemExit(f"Quota hit during search for query: {q}")
            break
        items=res.get("items",[])
        out.extend(items)
        tok=res.get("nextPageToken")
        if not tok or len(out)>=max_results: break
        time.sleep(0.2)
    return out[:max_results]

def fetch_transcript(video_id):
    try:
        t=YouTubeTranscriptApi.get_transcript(video_id,languages=["en"])
        return " ".join(seg["text"] for seg in t)
    except (TranscriptsDisabled, NoTranscriptFound, Exception):
        return ""

def proximity_context(text, token, keywords, window_chars=120):
    t=text.lower()
    if token not in t: return False
    for kw in keywords:
        pattern = rf"{re.escape(token)}(.{{0,{window_chars}}}){re.escape(kw)}|{re.escape(kw)}(.{{0,{window_chars}}}){re.escape(token)}"
        if re.search(pattern, t):
            return True
    return False

def is_relevant(brand_key, title, desc, transcript):
    cfg = BRANDS[brand_key]
    t_all = (title + " " + desc + " " + transcript).lower()

    hard_negatives = [
        "weaving","knitting","knit","crochet","bracelet","rug","yarn","textile",
        "cloth","fabric","sewing","bead loom","card weaving","paper loom","pattern",
        "handmade","threads","needle","toy loom","macrame","craft","cardboard","weaver",
        "gamma rays","gamma radiation","hdr gamma","greek letter","scientific gamma",
        "romantic","love story","dating","couples","valentine","romantic song","relationship"
    ]
    if any(n in t_all for n in (cfg["negatives"] + hard_negatives)):
        return False

    has_brand_alias = any(alias in t_all for alias in cfg["brand_aliases"])
    has_domain = any(d in t_all for d in cfg["domains"])
    if not (has_brand_alias or has_domain):
        return False

    has_required = any(term in t_all for term in cfg["required_terms"])
    if not (has_required or has_domain):
        return False

    if brand_key == "loom":
        if not proximity_context(t_all, "loom", [
            "screen","record","screen recorder","screen record","screen capture",
            "video message","async video","chrome extension","desktop recorder","meeting"
        ], window_chars=90):
            if not has_domain:
                return False

    if brand_key == "clueso ai":
        music_terms = ["music","song","album","lyrics","rapper","concert","tour","singer","hip hop","pop music","live"]
        if any(m in t_all for m in music_terms):
            return False
        if (" ai" not in t_all) and (not has_domain):
            return False

    if brand_key == "emergent ai":
        if (" ai" not in t_all) and (not has_domain):
            return False

    # Special: Synthesia — avoid piano/game/music/neurology
    if brand_key == "synthesia":
        # Make sure it's about avatars/text-to-video; allow domain shortcut
        avatar_terms = ["avatar","presenter","text to video","text-to-video","talking head","studio","lip sync","lipsync","elearning","training","localize"]
        if not (has_domain or any(a in t_all for a in avatar_terms)):
            return False

    return True

def extract_contacts(text):
    emails=re.findall(r'[\w\.-]+@[\w\.-]+\.\w+',text)
    emails=[e for e in emails if not e.lower().endswith((".png",".jpg",".gif",".webp",".svg"))]
    emails=list(dict.fromkeys(emails))
    insta=None; xprof=None
    m=re.search(r'(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?',text,re.I)
    if m: insta="https://instagram.com/"+m.group(1)
    m2=re.search(r'(?:https?://)?(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)/?',text,re.I)
    if m2: xprof="https://x.com/"+m2.group(1)
    return emails,insta,xprof

def scrape_channel_about_requests(cid):
    try:
        r=requests.get(f"https://www.youtube.com/channel/{cid}/about",
                       headers={"User-Agent":USER_AGENT},timeout=REQUEST_TIMEOUT)
        if r.status_code!=200: return {}
        soup=BeautifulSoup(r.text,"html.parser")
        txt=soup.get_text(" ",strip=True)
        e,i,x=extract_contacts(txt)
        return {"emails":e,"instagram":i,"x_profile":x}
    except: return {}

def get_selenium_driver():
    try:
        opts=Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--mute-audio")
        opts.add_argument("--autoplay-policy=user-required")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_experimental_option("prefs", {
            "profile.default_content_setting_values.sound": 2,
            "profile.managed_default_content_settings.images": 2
        })
        service=Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service,options=opts)
    except Exception:
        return None

def scrape_channel_about_selenium(cid,driver):
    try:
        driver.get(f"https://www.youtube.com/channel/{cid}/about")
        time.sleep(2.5)
        soup=BeautifulSoup(driver.page_source,"html.parser")
        txt=soup.get_text(" ",strip=True)
        e,i,x=extract_contacts(txt)
        return {"emails":e,"instagram":i,"x_profile":x}
    except:
        return {}

def batched_video_meta(svc,vids):
    out={}; vids=list(dict.fromkeys(vids))
    for i in tqdm(range(0,len(vids),50),desc="Fetching video metadata"):
        chunk=vids[i:i+50]
        try:
            res=svc.videos().list(part="statistics,snippet",id=",".join(chunk)).execute()
        except HttpError as e:
            if e.resp.status==403: raise SystemExit("Quota hit during enrichment.")
            raise
        for it in res.get("items",[]):
            vid=it["id"]; stats=it.get("statistics",{}); snip=it.get("snippet",{})
            out[vid]={
                "views":int(stats.get("viewCount",0)) if stats.get("viewCount") else None,
                "title":snip.get("title"),
                "desc":snip.get("description",""),
                "cid":snip.get("channelId"),
                "channel":snip.get("channelTitle")
            }
        time.sleep(0.2)
    return out

def queries_for(brand):
    cfg=BRANDS[brand]
    q=[]
    # required terms
    for term in cfg["required_terms"]:
        q.append(f'"{brand}" {term}')
    # aliases + ai+intents
    for alias in cfg["brand_aliases"]:
        for w in ["ai","tutorial","demo","review","setup","overview","use case","walkthrough","features","pricing","integration","product"]:
            q.append(f'"{alias}" {w}')
    # domains
    for d in cfg["domains"]:
        q.append(f'"{brand}" "{d}"')
        for alias in cfg["brand_aliases"]:
            q.append(f'"{alias}" "{d}"')
    # software/app hints
    q.append(f'"{brand}" software')
    q.append(f'"{brand}" app')
    return list(dict.fromkeys(q))

# ============================= PIPELINE =============================

def search_and_filter(svc, brands, per_query, target_per_brand, order, duration):
    rows=[]
    for brand in brands:
        print(f"\n=== BRAND: {brand} ===")
        qs=queries_for(brand); seen=set(); b_rows=[]
        for q in tqdm(qs,desc=f"Queries[{brand}]",leave=False):
            items=youtube_search_paged(svc,q,per_query,order,duration)
            for it in items:
                vid=it["id"]["videoId"]
                if vid in seen: continue
                seen.add(vid)
                title=it["snippet"].get("title","")
                desc=it["snippet"].get("description","")
                transcript=fetch_transcript(vid)
                if is_relevant(brand,title,desc,transcript):
                    b_rows.append({"brand":brand,"videoId":vid,"video_url":f"https://www.youtube.com/watch?v={vid}","title":title})
                if len(b_rows)>=target_per_brand: break
            if len(b_rows)>=target_per_brand: break
            time.sleep(SLEEP_BETWEEN_SEARCHES)
        print(f"Found {len(b_rows)} STRICT relevant for {brand}")
        rows.extend(b_rows)
    return pd.DataFrame(rows)

def enrich_all(svc, df, use_selenium):
    if df is None or len(df)==0:
        return pd.DataFrame(columns=[
            "video_url","views","creator_email","instagram","x_profile","brand",
            "title","creator_channel","creator_channel_id","videoId"
        ])

    vids=df["videoId"].tolist()
    meta=batched_video_meta(svc,vids)
    driver=get_selenium_driver() if use_selenium else None
    out=[]
    for _,r in tqdm(df.iterrows(),total=len(df),desc="Enriching"):
        vid=r["videoId"]; m=meta.get(vid,{})
        desc=m.get("desc","")
        e_desc,i_desc,x_desc = extract_contacts(desc)

        cid=m.get("cid"); about={}
        if cid:
            about=scrape_channel_about_requests(cid)
            if use_selenium and driver and not (about.get("emails") or about.get("instagram") or about.get("x_profile")):
                about=scrape_channel_about_selenium(cid,driver) or about

        emails_about = about.get("emails", []) if about else []
        final_email = e_desc[0] if e_desc else (emails_about[0] if emails_about else None)

        out.append({
            "video_url":f"https://www.youtube.com/watch?v={vid}",
            "views":m.get("views"),
            "creator_email":final_email,
            "instagram":i_desc or (about.get("instagram") if about else None),
            "x_profile":x_desc or (about.get("x_profile") if about else None),
            "brand":r["brand"],
            "title":m.get("title"),
            "creator_channel":m.get("channel"),
            "creator_channel_id":cid,
            "videoId":vid
        })
        time.sleep(0.1)
    if driver:
        try: driver.quit()
        except: pass
    return pd.DataFrame(out)

def save_or_append_excel(path, df, key="videoId"):
    if os.path.exists(path):
        try:
            old=pd.read_excel(path)
            combined=pd.concat([old,df],ignore_index=True)
            combined.drop_duplicates(subset=[key],keep="first",inplace=True)
            combined.to_excel(path,index=False)
        except PermissionError:
            raise SystemExit(f"Close the Excel file '{path}' and rerun.")
    else:
        df.to_excel(path,index=False)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--api-key",type=str,default=None)
    ap.add_argument("--brands",nargs="*",default=list(BRANDS.keys()))
    ap.add_argument("--per-query",type=int,default=150)
    ap.add_argument("--target-per-brand",type=int,default=350)
    ap.add_argument("--video-duration",type=str,default="medium",choices=["any","short","medium","long"])
    ap.add_argument("--order",type=str,default="relevance",choices=["relevance","date","viewCount"])
    ap.add_argument("--final-xlsx",type=str,default="final_enriched.xlsx")
    ap.add_argument("--candidates-xlsx",type=str,default="candidates.xlsx")
    ap.add_argument("--append",action="store_true")
    ap.add_argument("--no-selenium",action="store_true")
    args=ap.parse_args()

    api=args.api_key or os.getenv("YOUTUBE_API_KEY")
    if not api: raise SystemExit("Provide --api-key or export YOUTUBE_API_KEY")

    svc=build_service(api)

    filtered=search_and_filter(svc,args.brands,args.per_query,args.target_per_brand,args.order,args.video_duration)
    if args.append: save_or_append_excel(args.candidates_xlsx,filtered,"videoId")
    else: filtered.to_excel(args.candidates_xlsx,index=False)
    print(f"Saved {len(filtered)} candidates to {args.candidates_xlsx} ({'appended' if args.append else 'overwrote'})")

    final=enrich_all(svc,filtered,use_selenium=(not args.no_selenium))
    if args.append: save_or_append_excel(args.final_xlsx,final,"videoId")
    else: final.to_excel(args.final_xlsx,index=False)
    print(f"Saved {len(final)} enriched rows to {args.final_xlsx} ({'appended' if args.append else 'overwrote'})")

if __name__=="__main__":
    main()
