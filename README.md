# Scraping Networks

A small Python pipeline for enriching a list of people with their **LinkedIn profiles** and **personal websites** — and, optionally, their current role and any company they've founded.

It works by querying a web-search API and **verifying** what it finds, rather than scraping LinkedIn directly. The headline trick for accuracy: a candidate page that links *back* to a person's known LinkedIn profile is treated as confirmed.

## What's in here

| Script | Does | Reads → Writes |
|---|---|---|
| `find_linkedin.py` | Finds each person's LinkedIn profile URL | `people.csv` → `people_with_linkedin.csv` |
| `find_websites.py` | Finds each person's personal website (high precision) | `people_with_linkedin.csv` → `people_with_websites.csv` |

Run the two focused scripts in order (`find_linkedin` then `find_websites`); together they are the higher-accuracy path. They enrich **LinkedIn** and **personal website** only — current affiliation and any founded company are out of scope for these two scripts.

> The data files (`*.csv`) are intentionally **not** committed (see `.gitignore`). Bring your own `people.csv`.

## Requirements

- Python 3.8+
- `requests` (`pip install requests`)
- API keys (below)

### API keys

| Key | Used by | Required? | Where to get it |
|---|---|---|---|
| `SERPER_KEY` | all scripts | **Required** | serper.dev |
| `ANTHROPIC_API_KEY` | `find_websites.py` | Recommended | console.anthropic.com |
| `GITHUB_TOKEN` | `find_websites.py` | Recommended | github.com/settings/tokens|


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

Both scripts are resumable.

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
- **`guess+...`** — the URL came from domain-guessing, not search.


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
