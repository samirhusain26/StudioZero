// Build the Checkpoint 1 question pack (HTML) from the checked question set.
//   node engines/motion/pipeline/pack.mjs --set=<questions-set> [--batch=<batchId>] [--dir=<batch dir>] [--out=<file.html>]
// Defaults: --set questions-2026-10 (the frozen regression set), --batch = first of CONFIG.batches,
// --out <batch dir>/review/question-pack.html. Prose comes from CONFIG.pack (optional) with generic defaults.
// Refuses to write into a finalized batch (READY_FOR_UPLOAD).
import {readFileSync, writeFileSync, existsSync, mkdirSync} from 'node:fs';
import {resolve, dirname, relative} from 'node:path';
import {ROOT, loadSet, DIFFICULTIES} from './lib.mjs';

const args = Object.fromEntries(process.argv.slice(2).map(a => a.replace(/^--/, '').split('=')));
const S = await loadSet(args.set ?? args.questions ?? 'questions-2026-10');
const C = S.config, P = C.pack ?? {};
const doc = JSON.parse(readFileSync(S.checkedPath, 'utf8'));
const cand = JSON.parse(readFileSync(S.candidatesPath, 'utf8'));
const BATCH = resolve(ROOT, args.dir ?? `library/${args.batch ?? C.batches[0]}`);
const out = resolve(ROOT, args.out ?? resolve(BATCH, 'review/question-pack.html'));
for (let d = dirname(out); d.startsWith(resolve(ROOT, 'library')) && d !== resolve(ROOT, 'library'); d = dirname(d))
  if (existsSync(resolve(d, 'READY_FOR_UPLOAD'))) throw new Error(`${relative(ROOT, d)} is finalized; write the pack elsewhere (--out=).`);
const verPath = resolve(ROOT, C.verification ?? resolve(BATCH, 'review/source-verification.json'));
const ver = existsSync(verPath) ? JSON.parse(readFileSync(verPath, 'utf8')) : null;
const verBy = Object.fromEntries((ver?.results ?? []).map(r => [r.key, r]));
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const GAMES = {scalar: ['Scalar', '#14B8A6'], continuum: ['Continuum', '#F472B6'], whenabouts: ['Whenabouts', '#EAB308'], tectonic: ['Tectonic', '#F2A154']};
const DIFF = {approachable: 'A', moderate: 'M', challenging: 'C'};

function shown(q) {
  const rows = [];
  if (q.prompt) rows.push(`<div class="prompt">${esc(q.prompt)}</div>`);
  if (q.clues) rows.push(`<ol class="clues">${q.clues.map((c, i) => `<li>${esc(c)} <span class="n">${q.evidence.checks.candidateCounts?.[i] ?? ''} left</span></li>`).join('')}</ol>`);
  if (q.shown) rows.push(`<div class="shown">Shown neighbors: ${q.shown.map(s => `<b>${esc(s.label)}</b>`).join(' · ')}</div>`);
  if (q.anchors) rows.push(`<div class="shown">Anchors: ${q.anchors.map(a => `<b>${esc(a.label)}</b> ${esc(a.text)}`).join(' &lt; ')}</div>`);
  rows.push(`<div class="choices">${q.choices.map(c => `<span class="${c.key === q.answerKey ? 'ans' : ''}">${c.key}) ${esc(c.label)}</span>`).join('')}</div>`);
  return rows.join('');
}
function card(q) {
  const v = verBy[q.key];
  const vbadge = v ? `<span class="v ${v.resolution ? 'pass' : v.status}">source check: ${esc(v.status)}${v.resolution ? ' → resolved' : ''}</span>` : '<span class="v pending">source check: pending</span>';
  const checks = Object.entries(q.evidence.checks).filter(([k]) => !['uniqueAnswer'].includes(k)).map(([k, val]) => `${esc(k)}: <code>${esc(typeof val === 'object' ? JSON.stringify(val) : val)}</code>`).join(' · ');
  return `<article class="${q.spare ? 'spare' : ''}">
  <header><span class="tag" style="background:${GAMES[q.game][1]}">${GAMES[q.game][0]}</span><span class="fmt">${esc(q.format)}</span>
  <span class="d d${DIFF[q.difficulty]}">${esc(q.difficulty)}</span>${q.pilot ? '<span class="pilot">PILOT</span>' : ''}${q.spare ? '<span class="sp">spare</span>' : ''}${vbadge}</header>
  <div class="hook">${esc(q.hook)}</div><h3>${esc(q.question)}</h3>
  ${shown(q)}
  <div class="row"><b>Answer</b> ${esc(q.answerKey)} · ${esc(q.answer)}</div>
  <div class="row"><b>Explanation</b> ${esc(q.explanation)}</div>
  <div class="row"><b>Why this difficulty</b> ${esc(q.rationale)}</div>
  ${q.editorialNote ? `<div class="row warn"><b>Editorial note</b> ${esc(q.editorialNote)}</div>` : ''}
  ${q.sensitiveReview ? `<div class="row warn"><b>Editorial note</b> ${esc(q.sensitiveReview)}</div>` : ''}
  <div class="row small"><b>Destination</b> scalargame.com${esc(q.destination.deepLink)} · <b>questionId</b> <code>${esc(q.questionId)}</code> · <b>review by</b> ${esc(q.reviewBy)}</div>
  <div class="row small"><b>Checks</b> ${checks}</div>
  <div class="row small"><b>Sources</b><ul>${q.evidence.sources.map(s => `<li><a href="${esc(s.url)}">${esc(s.title)}</a> (retrieved ${esc(s.retrieved)})</li>`).join('')}</ul></div>
  ${v?.notes ? `<div class="row small ${v.status === 'pass' || v.resolution ? '' : 'warn'}"><b>Independent check</b> ${esc(v.notes)}</div>` : ''}
  ${v?.resolution ? `<div class="row small"><b>Resolution</b> ${esc(v.resolution)}</div>` : ''}
</article>`;
}

const counts = {
  scalar: cand.scalar.progressiveClues.length + cand.scalar.candidateElimination.length,
  continuum: cand.continuum.headToHead.length + cand.continuum.missingSlot.length,
  whenabouts: cand.whenabouts.guessTheYear.length + cand.whenabouts.beforeAfter.length,
  tectonic: cand.tectonic.neighborClues.length + cand.tectonic.missingCountry.length,
};

const main = doc.questions.filter(q => !q.spare);
const title = P.title ?? C.batches.join(' + ');
const ctx = {doc, cand, ver, esc, counts, config: C};
function defaultIntro() {
  const rows = Object.entries(C.scope).map(([gf, n]) => `${n} ${gf.replace('/', ' ')}`).join(', ');
  const mix = DIFFICULTIES.map(d => `${main.filter(q => q.difficulty === d).length} ${d}`).join(' / ');
  const pilots = main.filter(q => q.pilot).length;
  return `Checkpoint 1. ${main.length} question${main.length === 1 ? '' : 's'} (${esc(rows)}; ${mix}) plus ${doc.questions.length - main.length} spare${doc.questions.length - main.length === 1 ? '' : 's'}${pilots ? `, ${pilots} marked as pilots` : ''}. Nothing is rendered yet.`;
}

const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Question Pack ${esc(title)}</title><style>
:root{--bg:#FAFAF9;--fg:#18181B;--mut:#52525B;--line:#E2E8F0;--card:#fff;--ok:#15803D;--warn:#B45309;--bad:#B91C1C}
@media (prefers-color-scheme:dark){:root{--bg:#111113;--fg:#F4F4F5;--mut:#A1A1AA;--line:#27272A;--card:#18181B;--ok:#4ADE80;--warn:#FBBF24;--bad:#F87171}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:16px;max-width:980px;margin:auto}
h1{font-size:26px;margin:.2em 0}h2{margin-top:2em;border-bottom:2px solid var(--fg);padding-bottom:4px}h3{margin:.2em 0 .4em;font-size:19px}
article{background:var(--card);border:1px solid var(--line);padding:14px 16px;margin:12px 0}article.spare{opacity:.85;border-style:dashed}
header{display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:12px;margin-bottom:6px}
.tag{color:#18181B;font-weight:700;padding:2px 8px}.fmt{font-family:ui-monospace,monospace}.d{padding:1px 7px;border:1px solid var(--line)}
.pilot{background:var(--fg);color:var(--bg);padding:1px 7px;font-weight:700}.sp{border:1px dashed var(--mut);padding:1px 7px}
.v{margin-left:auto;font-family:ui-monospace,monospace}.v.pass{color:var(--ok)}.v.concern{color:var(--warn)}.v.fail{color:var(--bad)}.v.pending{color:var(--mut)}
.hook{color:var(--mut);font-size:13px;text-transform:uppercase;letter-spacing:.06em}.prompt{font-size:17px;font-style:italic;margin:.2em 0}
.clues{margin:.3em 0 .3em 1.2em;padding:0}.clues .n{color:var(--mut);font-size:12px;font-family:ui-monospace,monospace}
.choices{display:flex;flex-wrap:wrap;gap:6px;margin:.5em 0}.choices span{border:1px solid var(--line);padding:2px 8px}.choices .ans{border:2px solid var(--ok);font-weight:700}
.row{margin:.25em 0}.small{font-size:13px;color:var(--mut)}.small b{color:var(--fg)}.warn{color:var(--warn)}code{font-size:12px}
ul{margin:.2em 0 .2em 1.2em;padding:0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.ask{border-left:4px solid var(--fg);padding:6px 12px;background:var(--card);margin:10px 0}.ask h4{margin:.2em 0}
pre{background:var(--card);border:1px solid var(--line);padding:10px;overflow-x:auto;font-size:13px}
</style></head><body>
<h1>Scalar social quiz library · Question pack ${esc(title)}</h1>
<p>${P.intro ? P.intro(ctx) : defaultIntro()}</p>
<table><tr><th>Snapshot</th><td><code>${esc(doc.snapshotId)}</code>, game commit <code>${esc(doc.gameCommit.slice(0, 7))}</code>${P.snapshotNote ?? ' (committed HEAD only)'}, hash <code>${esc(doc.snapshotHash.slice(0, 16))}…</code></td></tr>
<tr><th>Question set</th><td><code>${esc(doc.questionsHash.slice(0, 16))}…</code>, checked for ${esc(doc.checkedFor)}, review-by ${esc(doc.reviewBy)}</td></tr>
<tr><th>Candidates generated</th><td>Scalar ${counts.scalar} · Continuum ${counts.continuum} · Whenabouts ${counts.whenabouts} (strict freshness) · Tectonic ${counts.tectonic}</td></tr>
<tr><th>Deterministic checks</th><td>Unique answer within the 195-country universe (Scalar progressive clues, Tectonic neighbor clues); each elimination clue removes a candidate; numeric clues ambiguous within ±3% count both ways; game data and the pinned World Bank/Factbook references must agree; Continuum order identical in game data and World Bank, adjacent ratio ≥1.15 (population) / ≥1.10 (area), one reference year; Whenabouts events appear only in Dailies ended on or before ${esc(doc.latestEndedDate)} (UTC−12 + 4-day buffer), reviewed fact fingerprint matches the event, no number in titles; Tectonic land neighbors agree in Factbook and globe adjacency; no Scalar answer is a Countries Daily pick ${esc(doc.checkedFor)} → ${esc(doc.reviewBy)}; no repeat of the published legacy ep01–ep08 questions; D13 sensitive/contested exclusions; no subject repeats within a game; answer absent from pre-reveal text; every explanation number and list is filled from data, and hand-written claims carry asserts.${P.checksNote ?? ' No questionId or episode ID already used in an earlier batch (library/*/batch.json and frozen job inputs).'} Mutation tests confirmed the checker rejects broken questions.</td></tr>
<tr><th>Independent source check</th><td>${ver ? esc(ver.summary) + (P.sourceCheckNote ?? '') : `Pending: the fact-checker writes <code>${esc(relative(ROOT, verPath))}</code>.`}</td></tr></table>
${P.notes ? P.notes(ctx) : '\n'}${Object.keys(GAMES).filter(g => doc.questions.some(q => q.game === g)).map(g => `<h2>${GAMES[g][0]}</h2>${doc.questions.filter(q => q.game === g && !q.spare).map(card).join('')}<details><summary>Spares (${doc.questions.filter(q => q.game === g && q.spare).length})</summary>${doc.questions.filter(q => q.game === g && q.spare).map(card).join('')}</details>`).join('')}
</body></html>`;
mkdirSync(dirname(out), {recursive: true});
writeFileSync(out, html);
console.log(out);
