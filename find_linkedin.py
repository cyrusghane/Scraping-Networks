#!/usr/bin/env python3
"""
find_linkedin.py

First pass: for each person in a CSV, run one web search and pull out their
LinkedIn profile URL. 

Columns written per person:
  - "LinkedIn"         : the linkedin.com/in/... profile URL (blank if none found)
  - "linkedin_match"   : the title of the result the URL came from, so you can
                         eyeball that it's the RIGHT person (helps catch
                         same-name mismatches). Delete this column as desired.

Results are written incrementally and anyone already
in the output file is skipped -- so if it stops, errors, or hits a quota, just
run it again and it resumes where it left off.

SETUP:
  1. pip install requests
  2. Sign up at serper.dev, paste the key below (or set it as an env var).
  3. Export your sheet as people.csv (must have a name column).
  4. python find_linkedin.py
"""

import csv
import os
import re
import sys
import time
import requests

# ----------------------------- CONFIG --------------------------------------

SEARCH_PROVIDER = "serper"               # "serper" | "serpapi" | "google"

SERPER_KEY     = os.environ.get("SERPER_KEY",     "PASTE_KEY_HERE")
SERPAPI_KEY    = os.environ.get("SERPAPI_KEY",    "PASTE_KEY_HERE")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "PASTE_KEY_HERE")
GOOGLE_CX      = os.environ.get("GOOGLE_CX",      "PASTE_CX_HERE")

INPUT_CSV  = "people.csv"
OUTPUT_CSV = "people_with_linkedin.csv"

NAME_COLUMN    = "Name"                  # column holding the person's name
COMPANY_COLUMN = "Company"               # optional hint to disambiguate; "" to skip
CONTEXT_SUFFIX = "ex-Y Combinator"       # extra query keywords to pin the right person

PAUSE_SECONDS = 0.5
MAX_RETRIES   = 3

# ---------------------------------------------------------------------------

def _norm(items):
    return [{"title": it.get("title", ""),
             "link": it.get("link", ""),
             "snippet": it.get("snippet", "")} for it in (items or [])]

def search_serper(query):
    r = requests.post("https://google.serper.dev/search",
                      headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
                      json={"q": query, "num": 6}, timeout=20)
    r.raise_for_status()
    return _norm(r.json().get("organic", []))

def search_serpapi(query):
    r = requests.get("https://serpapi.com/search.json",
                     params={"engine": "google", "q": query, "api_key": SERPAPI_KEY, "num": 6},
                     timeout=20)
    r.raise_for_status()
    return _norm(r.json().get("organic_results", []))

def search_google(query):
    r = requests.get("https://www.googleapis.com/customsearch/v1",
                     params={"key": GOOGLE_API_KEY, "cx": GOOGLE_CX, "q": query, "num": 6},
                     timeout=20)
    r.raise_for_status()
    return _norm(r.json().get("items", []))

PROVIDERS = {"serper": search_serper, "serpapi": search_serpapi, "google": search_google}

def run_with_retry(fn, *args):
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args)
        except Exception as e:                  # transient network / rate-limit errors
            last = e
            wait = attempt * 2
            print(f"   retry {attempt}/{MAX_RETRIES}: {e} (waiting {wait}s)")
            time.sleep(wait)
    raise last

# Matches a profile URL (.../in/slug) but not posts/pulse/company pages
LINKEDIN_RE = re.compile(r"https?://[a-z]{0,3}\.?linkedin\.com/in/[^/?#\s\"']+", re.I)

def find_linkedin(results):
    """Return (url, title_of_matching_result)."""
    for r in results:                           # prefer the actual result link
        m = LINKEDIN_RE.search(r["link"])
        if m:
            return m.group(0), r["title"]
    for r in results:                           # fall back to a URL inside a snippet
        m = LINKEDIN_RE.search(r["snippet"])
        if m:
            return m.group(0), r["title"]
    return "", ""

def already_done(path):
    done = set()
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done.add(row.get(NAME_COLUMN, ""))
    return done

NEW_COLS = ["LinkedIn", "linkedin_match"]

def main():
    if SEARCH_PROVIDER not in PROVIDERS:
        sys.exit(f"Unknown SEARCH_PROVIDER: {SEARCH_PROVIDER}")
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Input file not found: {INPUT_CSV}")

    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("Input CSV is empty.")

    done = already_done(OUTPUT_CSV)
    write_header = not os.path.exists(OUTPUT_CSV)
    base_cols = [c for c in rows[0].keys() if c not in NEW_COLS]
    fieldnames = base_cols + NEW_COLS
    search_fn = PROVIDERS[SEARCH_PROVIDER]

    found = 0
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        for i, row in enumerate(rows, 1):
            name = (row.get(NAME_COLUMN) or "").strip()
            if not name or name in done:
                continue

            hint = (row.get(COMPANY_COLUMN) or "").strip() if COMPANY_COLUMN else ""
            query = " ".join(x for x in [name, hint, CONTEXT_SUFFIX, "LinkedIn"] if x)

            try:
                results = run_with_retry(search_fn, query)
            except Exception as e:
                print(f"[{i}/{len(rows)}] {name}  -> search failed: {e}")
                results = []

            url, match = find_linkedin(results)
            row["LinkedIn"] = url
            row["linkedin_match"] = match
            if url:
                found += 1
            print(f"[{i}/{len(rows)}] {name}  ->  {url or '(none)'}")

            writer.writerow(row)
            out.flush()                           # persist each row -> safe to resume
            time.sleep(PAUSE_SECONDS)

    print(f"\nDone. Found LinkedIn for {found} people. Results in {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
