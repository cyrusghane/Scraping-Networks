# Scraping Networks

A small Python pipeline for enriching a list of people with their **LinkedIn profiles** and **personal websites** — and, optionally, their current role and any company they've founded.

It works by querying a web-search API and **verifying** what it finds, rather than scraping LinkedIn directly. The headline trick for accuracy: a candidate page that links *back* to a person's known LinkedIn profile is treated as confirmed.

## What's in here

| Script | Does | Reads → Writes |
|---|---|---|
| `find_linkedin.py` | Finds each person's LinkedIn profile URL | `people.csv` → `people_with_linkedin.csv` |
| `find_websites.py` | Finds each person's personal website (high precision) | `people_with_linkedin.csv` → `people_with_websites.csv` |
| `linkedin_enrich.py` | All-in-one: LinkedIn + website + current role + founded company in one pass | `people.csv` → `people_enriched.csv` |

The two focused scripts (`find_linkedin` then `find_websites`) are the recommended, higher-accuracy path. `linkedin_enrich.py` does everything in a single pass with lighter verification — handy for a quick first cut.

> The data files (`*.csv`) are intentionally **not** committed (see `.gitignore`). Bring your own `people.csv`.

## Requirements

- Python 3.8+
- `requests` (`pip install requests`)
- API keys (below)

### API keys

| Key | Used by | Required? | Where to get it |
|---|---|---|---|
| `SERPER_KEY` | all scripts | **Required** | serper.dev |
| `ANTHROPIC_API_KEY` | `find_websites.py`, `linkedin_enrich.py` | Recommended | console.anthropic.com |
| `GITHUB_TOKEN` | `find_websites.py` | Recommended | github.com/settings/tokens (no scopes needed) |

`find_linkedin.py` needs only `SERPER_KEY`. The Anthropic key powers page verification and extraction — without it, `find_websites.py` falls back to a strict name-match heuristic (higher precision, lower recall). The GitHub token keeps the GitHub-profile lookup from rate-limiting.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install requests

export SERPER_KEY="..."
export ANTHROPIC_API_KEY="sk-ant-..."   # optional
export GITHUB_TOKEN="..."               # optional
```

The `export` lines and `source venv/bin/activate` are per-session — re-run them in each new terminal.

## Input

A CSV with a header row and at least a `Name` column. A `Company` column is optional but improves matching:

```csv
Name,Company
Kyle Corbitt,OpenPipe
Jane Doe,
```

If your columns are titled differently, edit `NAME_COLUMN` / `COMPANY_COLUMN` near the top of each script (or set `COMPANY_COLUMN = ""` to skip it).

## Usage

Run the two passes in order:

```bash
# 1. find LinkedIn URLs
python3 find_linkedin.py        # people.csv -> people_with_linkedin.csv

# 2. find personal websites (uses the LinkedIn URLs as an anchor)
python3 find_websites.py        # people_with_linkedin.csv -> people_with_websites.csv
```

Both scripts are **resumable**: they write results row-by-row and skip anyone already in the output file, so if a run stops (quota, network, Ctrl-C), just run it again and it picks up where it left off.

**Tip:** test on a small slice first — copy the header plus a handful of rows into a small CSV and point `INPUT_CSV` at it before processing the full list.

## Output columns

`find_linkedin.py` adds:

| Column | Meaning |
|---|---|
| `LinkedIn` | the `linkedin.com/in/...` profile URL (blank if none found) |
| `linkedin_match` | title of the result the URL came from — for spotting wrong-person matches |

`find_websites.py` adds:

| Column | Meaning |
|---|---|
| `personal_website` | the verified personal site (blank if none found) |
| `website_confidence` | 0–1 confidence in the match |
| `website_source` | how it was found — see below |
| `website_evidence` | one-line reason |

Read `website_source` as a trust signal:

- **`linkback`** — the page links to the person's known LinkedIn. Essentially certain.
- **`llm`** — Claude judged the page to be theirs. Trust scales with confidence.
- **`heuristic`** — strict name match (used when no Anthropic key is set).
- **`guess+...`** — the URL came from domain-guessing, not search. Verified the same way, but worth a glance.

## How it works

**Finding LinkedIn** is a search-plus-regex job: one query per person (`"name" company LinkedIn`), then pull the first `linkedin.com/in/...` URL out of the results.

**Finding websites** is harder, so it runs in two stages with verification at the core. Stage one gathers candidates from several targeted searches and from each person's GitHub "website" field, fetches each candidate page, and confirms identity before trusting it — the strongest signal being a page that links back to the person's known LinkedIn. Where there's no link-back, Claude reads the page and decides whether it belongs to this specific person. Stage two only runs for the people stage one left blank: it builds likely domains from the name and the LinkedIn handle (e.g. `kcorbitt.com`), fetches the ones that resolve, and runs them through the same verification at a higher confidence bar, since a guessed domain is a weaker starting point. Every kept result carries a confidence score and a source tag, so borderline matches are easy to review.

## Configuration

Common knobs at the top of `find_websites.py`:

| Setting | Default | Effect |
|---|---|---|
| `MIN_CONFIDENCE` | `0.70` | minimum confidence to keep a search-found site |
| `MIN_CONFIDENCE_GUESS` | `0.80` | stricter bar for domain-guessed sites |
| `MAX_CANDIDATES` | `6` | max pages fetched per person in stage 1 |
| `MAX_GUESS_ATTEMPTS` | `14` | max domains probed per blank person in stage 2 |
| `TRY_DOMAIN_GUESSES` | `True` | set `False` to skip stage 2 entirely |
| `SEARCH_PROVIDER` | `"serper"` | `serper`, `serpapi`, or `google` |

## Notes & limitations

- **Blanks are common and usually correct** — many people simply don't have a personal website. A blank means "not found," not "failed."
- **~100% is not achievable.** The pipeline optimizes for *precision* (few wrong attributions) plus a confidence column so the uncertain few are easy to hand-check.
- **Same-name ambiguity** is the main risk — use `linkedin_match` and the website confidence/source columns to catch mismatches.
- **Data can be stale** — search results lag reality, so a recent job change or fundraise may not show up yet.

## Responsible use

This project queries licensed search APIs and public profile data; it does **not** scrape LinkedIn or evade any site's access controls. Respect each provider's terms and rate limits, treat the enriched personal data responsibly, and note that `.gitignore` keeps your data CSVs out of the repo by design — don't commit other people's personal information to a public repo.

## License

No license specified. Add one (e.g. MIT) if you want others to reuse this.
