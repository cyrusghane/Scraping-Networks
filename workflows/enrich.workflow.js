// enrich.workflow.js — Claude Code Workflow that fans the enrichment out across
// many agents in parallel (one agent per person). This is the script that
// actually generated the enriched CSVs in this repo — run via the Claude Code
// `Workflow` tool, NOT node. enrich.py is the standalone, single-process
// equivalent for people without Claude Code.
//
//   args: [{ idx, name, role, suffix }, ...]   // pass the roster as JSON
//   returns: [{ idx, name, linkedin, linkedin_confidence, current_affiliation,
//               founded_company, founded_confidence, personal_website,
//               website_confidence, evidence }, ...]

export const meta = {
  name: 'people-enrich',
  description: 'Enrich people with LinkedIn, current affiliation, founded company, personal website',
  phases: [{ title: 'Enrich', detail: 'one agent per person, web-research + link-back verify' }],
}

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    idx: { type: 'integer' },
    name: { type: 'string' },
    linkedin: { type: 'string' },
    linkedin_confidence: { type: 'string', enum: ['high', 'medium', 'low', 'none'] },
    current_affiliation: { type: 'string' },
    founded_company: { type: 'string', description: 'ONLY if they FOUNDED it: "<url> // <year>" (// ? if year unknown; name if defunct). "" otherwise.' },
    founded_confidence: { type: 'string', enum: ['high', 'medium', 'low', 'none'] },
    personal_website: { type: 'string' },
    website_confidence: { type: 'string', enum: ['high', 'medium', 'low', 'none'] },
    evidence: { type: 'string' },
  },
  required: ['idx', 'name', 'linkedin', 'linkedin_confidence', 'current_affiliation',
             'founded_company', 'founded_confidence', 'personal_website', 'website_confidence', 'evidence'],
}

const people = typeof args === 'string' ? JSON.parse(args) : args

phase('Enrich')
const results = await parallel(people.map(p => () =>
  agent(
`You are enriching ONE person. Use web search + page fetches to find VERIFIED facts. Be precise and CONSERVATIVE — same-name people are the main risk; abstain (return "" with confidence "none"/"low") when you cannot confirm THIS person.

PERSON:
  name: ${p.name}
  context / role / tenure: ${p.role || '(unknown)'}
  network: ${p.suffix || '(none)'}

Use the role/tenure and network to disambiguate from same-name people.

FIND (only what you can confirm for THIS person):
1. LinkedIn — canonical https://www.linkedin.com/in/<slug>/ , confirmed it's this person; else "".
2. current_affiliation — where they work / what they do now; "" if unknown.
3. founded_company — did THIS person FOUND/co-found a company? Founding only. "<url> // <year founded>" ("// ?" if year unknown, company name if defunct/no site). "" otherwise.
4. personal_website — their OWN site/blog/portfolio (strongest signal: it links back to their LinkedIn). NOT a company site, social profile, wiki/news, or same-name person. "" if none.

Return the structured result. idx must be ${p.idx} and name must be "${p.name}".`,
    { label: p.name, phase: 'Enrich', schema: SCHEMA, agentType: 'general-purpose' }
  )
))

return results.filter(Boolean)
