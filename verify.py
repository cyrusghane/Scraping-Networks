#!/usr/bin/env python3
"""
verify.py — adversarial spot-check of the uncertain enrichments.

Re-checks every low/medium-confidence cell in an enriched CSV by re-researching
it from scratch with a SKEPTIC prompt ("try to refute this"). This is the step
that catches same-name mismatches that slipped through the first pass (e.g. a
LinkedIn URL that actually belongs to a different person who shares the name).

For each flagged cell it writes one of these back into the matching `*_conf`
column, and applies corrections/clears in place:
  - "high (verified)"   confirmed — trust it
  - "corrected"         value was wrong; replaced with the right one
  - "refuted->blank"    value was a wrong/same-name match; cell cleared
  - "uncertain"         couldn't confirm either way; left as-is, flagged

SETUP
  pip install -r requirements.txt
  export ANTHROPIC_API_KEY=sk-ant-...
  CSV="people_enriched.csv" CONTEXT_SUFFIX="Y Combinator" python3 verify.py
"""

import csv, json, os, re, sys, time
import anthropic

MODEL          = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
CSV_PATH       = os.environ.get("CSV", "people_enriched.csv")
NAME_COLUMN    = "Name"
CONTEXT_COLUMN = "Past Affiliation"
CONTEXT_SUFFIX = os.environ.get("CONTEXT_SUFFIX", "")
MAX_TOKENS     = 6000
MAX_RETRIES    = 4

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209",  "name": "web_fetch"},
]

# field label -> (value column, confidence column)
FIELDS = {
    "LinkedIn":         ("LinkedIn", "linkedin_conf"),
    "Personal website": ("Personal website", "website_conf"),
    "Company":          ("Company (if any) // status", "founded_conf"),
}

PROMPT = """You are ADVERSARIALLY verifying ONE enrichment claim about a specific person. Try hard to REFUTE it; only confirm if the evidence is solid. Same-name people are the main risk. Use web_search / web_fetch.

PERSON: {name}  (context: {role}; network: {suffix})
CLAIM — the "{field}" field currently = "{value}"

Rules by field:
- LinkedIn: the URL must be THIS exact person's profile (matches the network + their role/field/timeline). If it belongs to a same-name different person -> "refuted" (corrected_value ""). If a better profile exists -> "corrected".
- Personal website: must be THIS person's own site/blog/portfolio — NOT a company marketing site, social profile, wiki/news/aggregator, or same-name person. about.me / GitHub-pages personal sites count if personally theirs.
- Company (founded): the person must have actually FOUNDED/co-founded it (not merely worked there). Format "<url> // <year>" (or "<name> // <year-or-?>" if defunct/no site). If founder but URL/year wrong -> "corrected". Clear junk like "Tba".

Output ONLY a JSON object:
{{"verdict":"confirmed|refuted|corrected|uncertain","corrected_value":"value the cell SHOULD hold (same if confirmed; \\"\\" if refuted; fixed value if corrected)","reasoning":"1-2 sentences with the deciding evidence"}}"""


def parse_json(text):
    t = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    s, e = t.find("{"), t.rfind("}")
    try:
        return json.loads(t[s:e + 1]) if s != -1 else {}
    except Exception:
        return {}


def call_claude(client, prompt):
    messages = [{"role": "user", "content": prompt}]
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            for _ in range(6):
                resp = client.messages.create(
                    model=MODEL, max_tokens=MAX_TOKENS,
                    thinking={"type": "adaptive"}, tools=WEB_TOOLS, messages=messages)
                if resp.stop_reason == "pause_turn":
                    messages.append({"role": "assistant", "content": resp.content})
                    continue
                break
            return parse_json("".join(b.text for b in resp.content if b.type == "text"))
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            last = e
            time.sleep(attempt * 3)
    print(f"   call failed: {last}")
    return {}


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY first.")
    if not os.path.exists(CSV_PATH):
        sys.exit(f"Not found: {CSV_PATH}")

    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    fields = list(rows[0].keys())
    client = anthropic.Anthropic()

    counts = {"confirmed": 0, "corrected": 0, "refuted->blank": 0, "uncertain": 0}
    for i, row in enumerate(rows, 1):
        name = row.get(NAME_COLUMN, "").strip()
        role = (row.get(CONTEXT_COLUMN) or "").strip() if CONTEXT_COLUMN else ""
        for label, (col, confcol) in FIELDS.items():
            conf = row.get(confcol, "").strip().lower()
            val = row.get(col, "").strip()
            if conf not in ("low", "medium") or not val:
                continue
            res = call_claude(client, PROMPT.format(
                name=name, role=role or "(unknown)", suffix=CONTEXT_SUFFIX or "(none)",
                field=label, value=val))
            verdict = res.get("verdict", "uncertain")
            new = (res.get("corrected_value") or "").strip()
            if verdict == "confirmed":
                row[confcol] = "high (verified)"; counts["confirmed"] += 1
            elif verdict == "corrected":
                row[col] = new; row[confcol] = "corrected" if new else "refuted->blank"
                counts["corrected"] += 1
            elif verdict == "refuted":
                row[col] = ""; row[confcol] = "refuted->blank"; counts["refuted->blank"] += 1
            else:
                row[confcol] = "uncertain"; counts["uncertain"] += 1
            print(f"[{i}/{len(rows)}] {name} [{label}] -> {verdict}: {res.get('reasoning','')[:90]}")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"\nDone. {counts}")


if __name__ == "__main__":
    main()
