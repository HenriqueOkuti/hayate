export const meta = {
  name: 'research-fanout',
  description: 'Research 2-4 sub-questions in parallel from public sources, fact-check the key claims, and write one dated note in docs/research/',
  whenToUse: 'A Hayate decision needs facts on several independent sub-questions. args: {date: "YYYY-MM-DD", slug, question, topics: [..up to 4..]}',
  phases: [
    { title: 'Research', detail: 'one public-sources researcher per sub-question' },
    { title: 'Fact-check', detail: 'try to refute each topic\'s key claims' },
    { title: 'Write note', detail: 'combine into docs/research/<date>-<slug>.md' },
  ],
}

const A = args || {}
if (!A.date || !A.slug || !Array.isArray(A.topics) || A.topics.length === 0) {
  throw new Error('args must be {date: "YYYY-MM-DD", slug: "...", question: "...", topics: ["...", ...]}')
}
const topics = A.topics.slice(0, 4)
if (A.topics.length > 4) log(`Only the first 4 of ${A.topics.length} topics are researched; run again for the rest.`)

const FINDINGS = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    summary: { type: 'string' },
    claims: {
      type: 'array',
      items: {
        type: 'object',
        properties: { claim: { type: 'string' }, source: { type: 'string' } },
        required: ['claim', 'source'],
      },
    },
    unverified: { type: 'array', items: { type: 'string' } },
    notes_markdown: { type: 'string' },
  },
  required: ['topic', 'summary', 'claims', 'unverified', 'notes_markdown'],
}

const CHECK = {
  type: 'object',
  properties: {
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          status: { type: 'string', enum: ['confirmed', 'refuted', 'unclear'] },
          evidence: { type: 'string' },
        },
        required: ['claim', 'status', 'evidence'],
      },
    },
  },
  required: ['checks'],
}

const RULES =
  'Public sources only (WebSearch/WebFetch). Never use logged-in CLIs, cloud accounts or connected-account MCP servers, even read-only. ' +
  'Prefer primary sources (official docs, papers, model/dataset cards, license texts). Every fact needs a URL. Do not write or edit any files.'

const results = await pipeline(
  topics,
  (topic) =>
    agent(
      `Research for Hayate, a personal project distilling an LLM into a tiny, fast web-page categorizer (see README.md and docs/).\n` +
        `Overall question: ${A.question || '(none given)'}\nYour sub-question: ${topic}\n\n${RULES}\n\n` +
        `Return: a short summary; the 3-6 claims that matter most for a decision, each with its source URL; anything you could not confirm on a primary source under "unverified"; ` +
        `and notes_markdown, a complete Markdown section for this sub-question (tables welcome, inline source links, dates on prices and versions, one line per paragraph or list item with no hard wrapping).`,
      { label: `research: ${topic.slice(0, 40)}`, phase: 'Research', schema: FINDINGS },
    ),
  (found, topic) =>
    found &&
    agent(
      `Fact-check these claims for Hayate. Open each source and, where useful, one independent public source. Try to REFUTE each claim. ` +
        `Mark "unclear" if you cannot confirm it on a primary source.\n\n${RULES}\n\n${JSON.stringify(found.claims, null, 2)}`,
      { label: `check: ${topic.slice(0, 40)}`, phase: 'Fact-check', schema: CHECK },
    ).then((check) => ({ ...found, check })),
)

const done = results.filter(Boolean)
if (done.length < topics.length) log(`${topics.length - done.length} topic(s) failed and are missing from the note.`)

phase('Write note')
const path = `docs/research/${A.date}-${A.slug}.md`
const summary = await agent(
  `Write the research note ${path} for Hayate from the findings below. Edit no other file.\n` +
    `Structure: an H1 with the question; "Snapshot ${A.date}. Public sources only."; one section per topic built from its notes_markdown, ` +
    `correcting or flagging every claim the fact-check marked refuted or unclear; a combined "Sources (accessed ${A.date})" list; ` +
    `an "UNVERIFIED / uncertain" list that includes all unclear claims.\n` +
    `Then run \`npx --no-install markdownlint-cli2 --no-globs ${path}\` and fix any issues.\n` +
    `Return a summary of 300 words or less: key findings, refuted claims, and what this changes in the existing docs.\n\n` +
    `Findings:\n${JSON.stringify(done, null, 2)}`,
  { label: 'write note', phase: 'Write note' },
)

return {
  path,
  summary,
  refuted: done.flatMap((d) => ((d.check && d.check.checks) || []).filter((c) => c.status === 'refuted')),
}
