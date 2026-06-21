// verify.workflow.js — Claude Code Workflow that adversarially re-checks the
// low/medium-confidence enrichments, one skeptic agent per claim. This is the
// step that caught the same-name mismatches (e.g. a LinkedIn that belonged to a
// different person who shared the name). Run via the Claude Code `Workflow` tool.
// verify.py is the standalone equivalent.
//
//   args: [{ idx, name, role, suffix, field, value }, ...]
//   returns: [{ idx, name, field, verdict, corrected_value, reasoning }, ...]

export const meta = {
  name: 'people-verify',
  description: 'Adversarially verify low/medium-confidence enrichment claims',
  phases: [{ title: 'Verify', detail: 'one skeptic per claim' }],
}

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    idx: { type: 'integer' }, name: { type: 'string' }, field: { type: 'string' },
    verdict: { type: 'string', enum: ['confirmed', 'refuted', 'corrected', 'uncertain'] },
    corrected_value: { type: 'string', description: 'value the cell SHOULD hold: same if confirmed; "" if refuted; fixed value if corrected' },
    reasoning: { type: 'string' },
  },
  required: ['idx', 'name', 'field', 'verdict', 'corrected_value', 'reasoning'],
}

const claims = typeof args === 'string' ? JSON.parse(args) : args

phase('Verify')
const results = await parallel(claims.map(c => () =>
  agent(
`You are ADVERSARIALLY verifying ONE enrichment claim. Try hard to REFUTE it; only confirm if the evidence is solid. Same-name people are the main risk.

PERSON: ${c.name}  (context: ${c.role || '(unknown)'}; network: ${c.suffix || '(none)'})
CLAIM — the "${c.field}" field currently = "${c.value}"

Rules by field:
- LinkedIn: must be THIS exact person's profile (network + role/field/timeline match). Same-name different person -> "refuted" (corrected_value ""). Better profile exists -> "corrected".
- Personal website: must be THIS person's own site/blog/portfolio — NOT a company site, social profile, wiki/news/aggregator, or same-name person.
- Company (founded): person must have actually FOUNDED/co-founded it (not just worked there). Format "<url> // <year>" (or "<name> // <year-or-?>"). If founder but URL/year wrong -> "corrected". Clear junk like "Tba".

Return verdict, corrected_value (what the cell should hold), reasoning. idx=${c.idx}, name="${c.name}", field="${c.field}".`,
    { label: c.name + ': ' + c.field, phase: 'Verify', schema: SCHEMA, agentType: 'general-purpose' }
  )
))

return results.filter(Boolean)
