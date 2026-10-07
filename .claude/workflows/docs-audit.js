export const meta = {
  name: 'docs-audit',
  description: 'Audit Hayate docs for contradictions, stale facts, broken links and timeline drift, then verify each finding. Report only; edits nothing.',
  whenToUse: 'Before a milestone, after a batch of decisions or research, or roughly monthly. Optional args: {groups: [[file, ...], ...]}',
  phases: [
    { title: 'Audit', detail: 'one auditor per group of docs' },
    { title: 'Verify', detail: 'one skeptic re-checks every deduplicated finding' },
  ],
}

const GROUPS = (args && args.groups) || [
  ['README.md', 'CLAUDE.md', 'site/README.md'],
  ['docs/timeline.md', 'docs/decisions/README.md'],
  ['docs/stack.md'],
  ['docs/labels.md'],
  ['docs/data.md'],
  ['docs/models.md'],
  ['docs/measurement.md'],
]

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'number' },
          kind: { type: 'string', enum: ['contradiction', 'stale', 'broken-link', 'timeline-drift', 'unclear', 'other'] },
          issue: { type: 'string' },
          evidence: { type: 'string' },
          suggested_fix: { type: 'string' },
        },
        required: ['file', 'kind', 'issue', 'evidence', 'suggested_fix'],
      },
    },
  },
  required: ['findings'],
}

const VERDICTS = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: { index: { type: 'number' }, real: { type: 'boolean' }, reason: { type: 'string' } },
        required: ['index', 'real', 'reason'],
      },
    },
  },
  required: ['verdicts'],
}

phase('Audit')
const audits = await parallel(
  GROUPS.map((files) => () =>
    agent(
      `Audit these Hayate docs: ${files.join(', ')}. Read them, then cross-check against the rest of the repo ` +
        `(other docs/, docs/decisions/, the newest notes in docs/research/, the actual files and folders).\n` +
        `Look for: statements that contradict another doc; facts older than a newer research note or an accepted decision; ` +
        `relative links or images that don't exist; timeline rows whose status doesn't match the repo; unclear or misleading text.\n` +
        `Do NOT edit anything. Only report real, specific problems with evidence (quote both sides of a contradiction). Return an empty list if the docs are fine.`,
      { label: `audit: ${files.join(', ').slice(0, 50)}`, phase: 'Audit', schema: FINDINGS },
    ),
  ),
)

// Barrier is intentional: a contradiction is often reported from both docs, so dedupe across all groups first.
const seen = new Set()
const all = []
for (const r of audits.filter(Boolean)) {
  for (const f of r.findings) {
    const key = `${f.kind}|${f.issue.toLowerCase().replace(/[^a-z0-9]+/g, ' ').slice(0, 80)}`
    if (seen.has(key)) continue
    seen.add(key)
    all.push(f)
  }
}
log(`${all.length} unique finding(s) from ${GROUPS.length} groups.`)
if (all.length === 0) return { confirmed: [], rejected: [] }

phase('Verify')
const check = await agent(
  `You are a skeptic. For each numbered finding about the Hayate docs below, open the files and decide whether it is REAL ` +
    `(the problem exists exactly as described and fixing it is worthwhile). Default to real=false if the evidence doesn't hold up. ` +
    `Edit nothing.\n\n${all.map((f, i) => `[${i}] ${JSON.stringify(f)}`).join('\n')}`,
  { label: 'verify findings', phase: 'Verify', schema: VERDICTS },
)

const verdicts = new Map(((check && check.verdicts) || []).map((v) => [v.index, v]))
const confirmed = all.filter((_, i) => verdicts.get(i) && verdicts.get(i).real)
const rejected = all
  .map((f, i) => ({ ...f, reason: verdicts.get(i) ? verdicts.get(i).reason : 'not judged' }))
  .filter((_, i) => !(verdicts.get(i) && verdicts.get(i).real))
return { confirmed, rejected }
