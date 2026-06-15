#!/usr/bin/env python3
"""
find_websites.py

scrapes each person's personal website in two stages.

STAGE 1 - SEARCH + VERIFY:
  1. Cast a wide net: several targeted searches per person, plus the "website"
     field from their GitHub profile, to gather candidate URLs.
  2. Verify each candidate by actually fetching the page:
       * LINK-BACK (strongest): if the page links to the exact LinkedIn URL we
         already found, it's confirmed.
       * Otherwise Claude reads the page and judges it (if an Anthropic key is
         set). Without a key, falls back to a strict name-match heuristic.

STAGE 2 - DOMAIN GUESS (only for people Stage 1 left blank):
  Builds likely domains from the name and the LinkedIn handle (e.g. janedoe.com,
  jdoe.io, etc), fetches the ones that resolve, and runs them
  through the SAME verification - but at a HIGHER confidence bar, because a
  guessed domain is a weaker prior (parked pages / squatters / same-name people).
  Hits found this way are tagged with a "guess+" source so you can spot them.

Reads people_with_linkedin.csv (needs the LinkedIn column as an anchor) and
writes people_with_websites.csv. Resumable: rerun to pick up where it stopped.

KEYS / SETUP:
  - SERPER_KEY        (required)                 - search
  - ANTHROPIC_API_KEY (optional, recommended)    - page verification via Claude
  - GITHUB_TOKEN      (optional, recommended)    - so the GitHub lookup doesn't
        rate-limit. Create at github.com/settings/tokens (no scopes needed).
  pip install requests ; export the keys ; python3 find_websites.py
"""

import csv, json, os, re, sys, time, requests

# ----------------------------- CONFIG --------------------------------------
SERPER_KEY        = os.environ.get("SERPER_KEY", "PASTE_KEY_HERE")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")   # "" => skip LLM, use heuristic
ANTHROPIC_MODEL   = "claude-haiku-4-5"
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")        # "" => GitHub lookup best-effort

INPUT_CSV  = "people_with_linkedin.csv"
OUTPUT_CSV = "people_with_websites.csv"

NAME_COLUMN     = "Name"
LINKEDIN_COLUMN = "LinkedIn"
COMPANY_COLUMN  = "Company"        # set "" if your sheet has no such column
CONTEXT_SUFFIX  = "ex-Y Combinator"

MAX_CANDIDATES  = 6               # max pages fetched per person in Stage 1
MIN_CONFIDENCE  = 0.70            # keep a Stage-1 website at/above this confidence
PAGE_TIMEOUT    = 15

# Stage 2 (domain guessing)
TRY_DOMAIN_GUESSES   = True       # set False to skip Stage 2 entirely
MAX_GUESS_ATTEMPTS   = 14         # cap total domains tried per blank person
MIN_CONFIDENCE_GUESS = 0.80       # stricter bar for guessed domains
GUESS_TIMEOUT        = 8

PAUSE_SECONDS = 0.4
MAX_RETRIES   = 3

# Domains that are never a "personal website"
BLOCKED = (
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "tiktok.com", "youtube.com", "reddit.com", "crunchbase.com", "pitchbook.com",
    "bloomberg.com", "wikipedia.org", "google.com", "github.com", "gitlab.com",
    "angel.co", "wellfound.com", "producthunt.com", "apple.com", "amazon.com",
)

# ----------------------------- HELPERS -------------------------------------
def retry(fn, *a):
    last = None
    for i in range(1, MAX_RETRIES + 1):
        try:
            return fn(*a)
        except Exception as e:
            last = e
            time.sleep(i * 2)
    raise last

def serper(query):
    r = requests.post("https://google.serper.dev/search",
                      headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
                      json={"q": query, "num": 8}, timeout=20)
    r.raise_for_status()
    return [it.get("link", "") for it in (r.json().get("organic", []) or [])]

def github_blogs(name):
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    out = []
    try:
        r = requests.get("https://api.github.com/search/users",
                         params={"q": name, "per_page": 3}, headers=headers, timeout=20)
        if r.status_code != 200:
            return out
        for u in r.json().get("items", [])[:3]:
            ur = requests.get(u["url"], headers=headers, timeout=20)
            if ur.status_code == 200:
                blog = (ur.json().get("blog") or "").strip()
                if blog:
                    out.append(blog if blog.startswith("http") else "https://" + blog)
    except Exception:
        pass
    return out

TAGS    = re.compile(r"<[^>]+>")
HREFS   = re.compile(r'href=["\']([^"\']+)["\']', re.I)
TITLE   = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
SCRIPTS = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)

def fetch(url, timeout=PAGE_TIMEOUT):
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; enrichment-script)"})
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return None

def to_text(html):
    html = SCRIPTS.sub(" ", html)
    return re.sub(r"\s+", " ", TAGS.sub(" ", html)).strip()

def get_title(html):
    m = TITLE.search(html)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

def li_slug(url):
    m = re.search(r"linkedin\.com/in/([^/?#\s\"']+)", url or "", re.I)
    return m.group(1).lower().rstrip("/") if m else ""

def links_back(html, linkedin_url):
    slug = li_slug(linkedin_url)
    if not slug:
        return False
    return any(li_slug(h) == slug for h in HREFS.findall(html))

def host(url):
    m = re.match(r"https?://([^/]+)", url or "", re.I)
    return m.group(1).lower().replace("www.", "") if m else ""

def blocked(url):
    h = host(url)
    return any(h == b or h.endswith("." + b) for b in BLOCKED)

def heuristic_conf(name, url, text):
    """Used only when no Anthropic key is set. Strict: require the full name."""
    toks = [t.lower() for t in re.split(r"\s+", name) if len(t) > 1]
    if not toks:
        return 0.0
    tl = text.lower()
    if not all(t in tl for t in toks):           # every name token must appear
        return 0.0
    name_in_domain = any(t in host(url) for t in toks if len(t) > 2)
    return 0.85 if name_in_domain else 0.65

# ----------------------------- LLM VERIFY ----------------------------------
VERIFY_PROMPT = """Decide whether a web page is the PERSONAL website of ONE specific person.

PERSON:
  name: {name}
  company / context: {context}
  known LinkedIn: {linkedin}

CANDIDATE PAGE:
  url: {url}
  title: {title}
  text (truncated): {text}

A personal website is an individual's own site, blog, or portfolio. It is NOT a
social profile, a company marketing site (unless clearly this person's own
page), a directory, a news article, a wiki, a parked/for-sale domain, or a
DIFFERENT person who shares the name.

Return ONLY this JSON (no markdown, no other text):
{{"is_personal_site": true_or_false, "confidence": 0.0_to_1.0, "reason": "one short sentence"}}

Be conservative: if the page does not clearly belong to THIS specific person,
return false. Match on name PLUS corroborating details (their company, role, or
projects) - a name alone is not enough when the name is common."""

def llm_verify(name, context, linkedin, url, title, text):
    prompt = VERIFY_PROMPT.format(name=name, context=context, linkedin=linkedin,
                                  url=url, title=title, text=text[:3000])
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": ANTHROPIC_API_KEY,
                               "anthropic-version": "2023-06-01",
                               "content-type": "application/json"},
                      json={"model": ANTHROPIC_MODEL, "max_tokens": 200,
                            "messages": [{"role": "user", "content": prompt}]},
                      timeout=40)
    r.raise_for_status()
    blocks = r.json().get("content", [])
    t = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e == -1:
        return {"is_personal_site": False, "confidence": 0.0, "reason": "no parse"}
    try:
        return json.loads(t[s:e + 1])
    except Exception:
        return {"is_personal_site": False, "confidence": 0.0, "reason": "no parse"}

# ------------------------- SHARED VERIFICATION -----------------------------
def verify_candidate(name, context, linkedin, url, html, threshold):
    """Return a result dict if this page is THIS person's site, else None."""
    if links_back(html, linkedin):               # confirmed: links to exact LinkedIn
        return {"url": url, "confidence": 0.97, "source": "linkback",
                "reason": "page links to the person's known LinkedIn"}
    title, text = get_title(html), to_text(html)
    if ANTHROPIC_API_KEY:
        v = retry(llm_verify, name, context, linkedin, url, title, text)
        conf = float(v.get("confidence", 0) or 0)
        if bool(v.get("is_personal_site")) and conf >= threshold:
            return {"url": url, "confidence": round(conf, 2), "source": "llm",
                    "reason": (v.get("reason", "") or "")[:200]}
    else:
        conf = heuristic_conf(name, url, text)
        if conf >= threshold:
            return {"url": url, "confidence": conf, "source": "heuristic",
                    "reason": "strict name match (page + domain)"}
    return None

# ----------------------- STAGE 1: SEARCH + VERIFY --------------------------
def gather_candidates(name, company):
    queries = [f'"{name}" (personal website OR blog OR portfolio OR homepage)']
    if company:
        queries.append(f'"{name}" {company}')
    if CONTEXT_SUFFIX:
        queries.append(f'"{name}" {CONTEXT_SUFFIX}')
    urls = []
    for q in queries:
        try:
            urls += retry(serper, q)
        except Exception:
            pass
    urls += github_blogs(name)

    seen, out = set(), []
    for u in urls:
        if not u or not u.startswith("http") or blocked(u):
            continue
        norm = re.sub(r"[#?].*$", "", u).rstrip("/")
        key = host(norm) + re.sub(r"^https?://[^/]+", "", norm)
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)

    toks = [t.lower() for t in re.split(r"\s+", name) if len(t) > 2]
    out.sort(key=lambda u: -sum(1 for t in toks if t in host(u)))   # name-in-domain first
    return out

def stage1(name, context, company, linkedin):
    best, fetched = None, 0
    for url in gather_candidates(name, company):
        if fetched >= MAX_CANDIDATES:
            break
        html = fetch(url)
        if not html:
            continue
        fetched += 1
        res = verify_candidate(name, context, linkedin, url, html, MIN_CONFIDENCE)
        if res:
            if res["source"] == "linkback":
                return res
            if best is None or res["confidence"] > best["confidence"]:
                best = res
    return best

# ----------------------- STAGE 2: DOMAIN GUESSING --------------------------
def candidate_domains(name, linkedin):
    parts = [re.sub(r"[^a-z]", "", p.lower()) for p in re.split(r"\s+", name) if p]
    parts = [p for p in parts if p]
    slug = re.sub(r"[^a-z0-9]", "", li_slug(linkedin).lower())
    handles = []                                 # ordered by likelihood
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        handles += [first + last, first[0] + last, first + last[0], first + "-" + last]
    elif parts:
        handles += [parts[0]]
    if slug and slug not in handles:
        handles.insert(0, slug)                  # LinkedIn handle is a strong guess
    handles = [h for h in dict.fromkeys(handles) if len(h) >= 4]
    tlds = [".com", ".io", ".me", ".dev", ".co", ".ai"]
    return [f"https://{h}{tld}" for h in handles for tld in tlds]

def stage2_guess(name, context, linkedin):
    best, attempts = None, 0
    for url in candidate_domains(name, linkedin):
        if attempts >= MAX_GUESS_ATTEMPTS:
            break
        attempts += 1
        html = fetch(url, timeout=GUESS_TIMEOUT)
        if not html:
            continue
        res = verify_candidate(name, context, linkedin, url, html, MIN_CONFIDENCE_GUESS)
        if res:
            res["source"] = "guess+" + res["source"]
            if res["source"].endswith("linkback"):
                return res
            if best is None or res["confidence"] > best["confidence"]:
                best = res
    return best

# ----------------------------- MAIN ----------------------------------------
NEW_COLS = ["personal_website", "website_confidence", "website_source", "website_evidence"]

def already_done(path):
    done = set()
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(row.get(NAME_COLUMN, ""))
    return done

def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Input file not found: {INPUT_CSV} (run the LinkedIn pass first)")
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("Input CSV is empty.")
    if not ANTHROPIC_API_KEY:
        print("NOTE: no ANTHROPIC_API_KEY set -> using strict name-match heuristic only "
              "(higher precision, lower recall). Set the key for better coverage.\n")

    done = already_done(OUTPUT_CSV)
    write_header = not os.path.exists(OUTPUT_CSV)
    base_cols = [c for c in rows[0].keys() if c not in NEW_COLS]
    fieldnames = base_cols + NEW_COLS

    found = 0
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        for i, row in enumerate(rows, 1):
            name = (row.get(NAME_COLUMN) or "").strip()
            if not name or name in done:
                continue
            company  = (row.get(COMPANY_COLUMN) or "").strip() if COMPANY_COLUMN else ""
            linkedin = (row.get(LINKEDIN_COLUMN) or "").strip() if LINKEDIN_COLUMN else ""
            context  = " ".join(x for x in [company, CONTEXT_SUFFIX] if x)

            try:
                best = stage1(name, context, company, linkedin)
                if best is None and TRY_DOMAIN_GUESSES:
                    best = stage2_guess(name, context, linkedin)   # only for blanks
            except Exception as e:
                print(f"[{i}/{len(rows)}] {name}  -> error: {e}")
                best = None

            row["personal_website"]   = best["url"] if best else ""
            row["website_confidence"] = best["confidence"] if best else ""
            row["website_source"]     = best["source"] if best else ""
            row["website_evidence"]   = best["reason"] if best else ""

            if best:
                found += 1
                shown = f"{best['url']}  (confidence {best['confidence']}, via {best['source']})"
            else:
                shown = "(none)"
            print(f"[{i}/{len(rows)}] {name}  ->  {shown}")

            writer.writerow(row)
            out.flush()
            time.sleep(PAUSE_SECONDS)

    print(f"\nDone. Found a website for {found} people. Results in {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
