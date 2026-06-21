#!/usr/bin/env python3
"""
clean_sheet.py — deterministic clean-up pass before (or after) enrichment.

What it does, all without any API calls:
  - drops obvious CRM test/junk rows (configurable name+role pairs)
  - normalizes LinkedIn URLs to canonical https://www.linkedin.com/in/<slug>/
    (adds the scheme, strips ?query / #fragment / trailing slash)
  - moves a Wikipedia/news URL out of the "Personal website" column into notes
    (those aren't personal sites)
  - for people still at the org, sets a blank "Current Affiliation" to the org name

Reads INPUT_CSV, writes OUTPUT_CSV (the original is never modified), and dumps
the removed rows to REMOVED_CSV so nothing is lost silently.

  INPUT_CSV="YC Scraping - Sheet2.csv" ORG_NAME="Y Combinator" python3 clean_sheet.py
"""

import csv, os, re, sys

INPUT_CSV   = os.environ.get("INPUT_CSV", "people.csv")
OUTPUT_CSV  = os.environ.get("OUTPUT_CSV", "people_cleaned.csv")
REMOVED_CSV = os.environ.get("REMOVED_CSV", "_removed_test_rows.csv")
ORG_NAME    = os.environ.get("ORG_NAME", "")          # e.g. "Y Combinator"; "" to skip

NAME_COL      = "Name"
ROLE_COL      = "Past Affiliation"
CURRENT_COL   = "Current Affiliation"
LINKEDIN_COL  = "LinkedIn"
WEBSITE_COL   = "Personal website"
STILL_COL     = "Still at YC?"                         # set "" if your sheet has no such column
NOTES_COL     = "notes"

# (Name, Past Affiliation) pairs to drop — matched exactly so a real person is never nuked.
TEST_ROWS = {
    ("Ryan Test", "Drip Test Account"),
    ("Frank Demo", "Demo User"),
    ("Ryan Recruiting", "Recruiter"),
    ("Ryan Recruiter", "Recruiter"),
    ("Ryan Nonfounder", "Test Non"),
    ("Ryan Choi", "Recruiter"),
}
NON_PERSONAL_SITE = ("wikipedia.org",)


def norm_linkedin(u):
    u = (u or "").strip()
    if not u:
        return u
    if not u.startswith("http"):
        u = "https://" + u
    u = re.sub(r"[?#].*$", "", u)
    u = re.sub(r"^https?://(www\.)?", "https://www.", u)
    return u.rstrip("/") + "/"


def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Input file not found: {INPUT_CSV}")
    rows = list(csv.DictReader(open(INPUT_CSV, encoding="utf-8")))
    if not rows:
        sys.exit("Input CSV is empty.")
    fields = list(rows[0].keys())

    cleaned, removed, changes = [], [], []
    for r in rows:
        if (r.get(NAME_COL, "").strip(), r.get(ROLE_COL, "").strip()) in TEST_ROWS:
            removed.append(r); continue
        name = r.get(NAME_COL, "").strip()

        if LINKEDIN_COL in r:
            li, nli = r[LINKEDIN_COL].strip(), norm_linkedin(r.get(LINKEDIN_COL))
            if li != nli:
                r[LINKEDIN_COL] = nli; changes.append(f"LinkedIn normalized: {name}")

        if WEBSITE_COL in r and any(b in r[WEBSITE_COL] for b in NON_PERSONAL_SITE):
            url = r[WEBSITE_COL].strip(); r[WEBSITE_COL] = ""
            if NOTES_COL in r:
                r[NOTES_COL] = (r[NOTES_COL] + " " if r[NOTES_COL] else "") + f"Reference: {url}"
            changes.append(f"{name}: moved non-personal URL out of website -> notes")

        if ORG_NAME and STILL_COL in r and r.get(STILL_COL, "").strip().lower() == "yes" \
                and not r.get(CURRENT_COL, "").strip():
            r[CURRENT_COL] = ORG_NAME

        cleaned.append(r)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(cleaned)
    if removed:
        with open(REMOVED_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(removed)

    print(f"Wrote {OUTPUT_CSV}: {len(cleaned)} rows (removed {len(removed)} test rows -> {REMOVED_CSV})")
    for c in changes:
        print("  -", c)


if __name__ == "__main__":
    main()
