# Scraping Networks

Given a network (alumni list, Slack group, etc.), scrapes relevant attributes for each member, including LinkedIn URL, current affiliation, founded company status (and if so, more details like date founded, URL, etc.), and personal website. 

Every field is verified and cross-checked from as many directions as possible (e.g., whether a personal website links to the correct LinkedIn URL), thus generating an associated confidence tag (`high`/`medium`/`low`/`none`). Fields marked as low/medium undergo an adversarial second pass.

## Pipeline

```
  clean_sheet.py      drop test rows, normalize LinkedIn URLs, fix misfiled data
        │
  extract_roster.py   (only if your source is a Slack screen-capture PDF)
        │             pull the page images so you can transcribe names → CSV
        ▼
  enrich.py           per person: web-search → find 4 fields → link-back verify
        │             → fill blanks only, with confidence + evidence columns
        ▼
  verify.py           re-check every low/medium cell with a skeptic prompt;
                      confirm / correct / clear (catches same-name mismatches)
```

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
```

The default model is `claude-opus-4-8`; for a
cheap bulk run over hundreds of people set `ANTHROPIC_MODEL=claude-haiku-4-5`, for instance.

## Usage

```bash
# 1. (optional) clean the raw sheet
INPUT_CSV="people.csv" OUTPUT_CSV="people_cleaned.csv" ORG_NAME="Y Combinator" \
  python3 clean_sheet.py

# 2. (optional) if your source is a Slack screen-capture PDF, get the images,
#    then transcribe the names into a CSV with at least a `Name` column
python3 extract_roster.py "screencapture-....pdf" roster_imgs/

# 3. enrich — fills blanks only; resumable (re-run to continue after a stop)
INPUT_CSV="people_cleaned.csv" OUTPUT_CSV="people_enriched.csv" \
  CONTEXT_SUFFIX="Y Combinator" python3 enrich.py

# 4. spot-check the uncertain cells in place
CSV="people_enriched.csv" CONTEXT_SUFFIX="Y Combinator" python3 verify.py
```

`CONTEXT_SUFFIX` is the network that pins the right person (`"Y Combinator"`,
`"Square / Block"`, …). Input needs a `Name` column; a free-text hint column
(role, tenure, Slack status — set via `CONTEXT_COLUMN`, default `Past Affiliation`)
sharply improves disambiguation.

## Output columns

`enrich.py` fills these:

| Column | Meaning |
|---|---|
| `Current Affiliation` | where they are now |
| `Company (if any) // status` | **founded** company as `url // year` (blank unless they founded one) |
| `LinkedIn` | canonical `https://www.linkedin.com/in/<slug>/` |
| `Personal website` | their own site (blank is common and usually correct) |
| `linkedin_conf` / `website_conf` / `founded_conf` | per-cell confidence |
| `enrich_evidence` | note on how identity was confirmed + any same-name flag |

Read the confidence columns as a trust signal:

- **`linkback`** — site links to the known LinkedIn. Essentially certain.
- **`high` / `medium` / `low` / `none`** — the model's own confidence; `low`/`none` usually sit next to a deliberately-blank cell (it looked and abstained).
- After `verify.py`: **`high (verified)`** (re-confirmed), **`corrected`** (value fixed), **`refuted->blank`** (wrong match, cleared), **`uncertain`** (couldn't confirm — eyeball it).

Sort by these to triage; delete the four audit columns once you're satisfied.
