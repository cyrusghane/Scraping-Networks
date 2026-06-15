# Scraping Networks

Pulling personal websites.

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


## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install requests

export SERPER_KEY="..."
export ANTHROPIC_API_KEY="sk-ant-..."   # optional
export GITHUB_TOKEN="..."               # optional
```

The `export` lines and `source venv/bin/activate` are per-session.
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

Both scripts are **resumable**.

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
