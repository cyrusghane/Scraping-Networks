# workflows/ — Claude Code workflows (how the shipped CSVs were generated)

These are [Claude Code](https://claude.com/claude-code) **Workflow** scripts, not
Node programs. They fan the same prompts used by `../enrich.py` and `../verify.py`
out across many agents running in parallel (one agent per person / per claim),
which is how the enriched CSVs in this repo were actually produced — ~250 and
~300 people enriched per run, each agent doing its own web research.

They run via the Claude Code `Workflow` tool, which provides the `agent()`,
`parallel()`, and `phase()` primitives and gives each agent web-search access —
they will not run under `node`. If you don't have Claude Code, use the standalone
`../enrich.py` and `../verify.py` instead; they use the Anthropic API directly and
produce the same columns, just single-process.

| Workflow | Mirrors | Input (`args`) |
|---|---|---|
| `enrich.workflow.js` | `enrich.py` | `[{idx, name, role, suffix}, ...]` |
| `verify.workflow.js` | `verify.py` | `[{idx, name, role, suffix, field, value}, ...]` |

Both return structured JSON per item (schema-enforced); a thin driver merges the
results back into the sheet, filling blanks only, exactly as the standalone
scripts do. Failed/stalled agents come back `null` and are simply re-run.
