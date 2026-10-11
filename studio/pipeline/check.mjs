// Deterministically check the curated question set against the frozen snapshot and resolve it into
// immutable episode inputs.
//   node studio/pipeline/check.mjs [--questions=questions-<set>.mjs | --set=<path/to/set.mjs>]
// Default set: questions-2026-10 (the frozen regression set; its output must stay byte-identical).
// Batch rules (scope, difficulty mix, pilots, episode IDs) come from the set's CONFIG export.
// Exits non-zero (and writes nothing) if any question fails. Output:
//   <CONFIG.outDir ?? library/_sources/<snapshot>>/questions-<set>.json
import {writeFileSync, mkdirSync, existsSync, readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {DISPLAY_NAMES, loadSnapshot, buildScalar, SENSITIVE, CONTESTED, CONTESTED_MAP, safeLatest, upcomingScalarPicks, yearsBetween, yearLabel, MARGIN,
  loadSet, libraryEpisodes, nextEpisodeId, FORMAT_SHORT, DIFFICULTIES} from './lib.mjs';

const args = Object.fromEntries(process.argv.slice(2).map(a => a.replace(/^--/, '').split('=')));
const SET = await loadSet(args.questions ?? args.set ?? 'questions-2026-10');
const {SNAPSHOT, TODAY, QUESTIONS, WHENABOUTS_FRESHNESS = 'strict', config: CONFIG} = SET;
const snap = loadSnapshot(SNAPSHOT);
const S = buildScalar(snap);
const name = id => S.byId[id]?.name ?? S.globeById[id]?.name ?? id;
const LATEST = safeLatest(new Date(`${TODAY}T12:00:00Z`));
const picks = await upcomingScalarPicks(snap, TODAY, 90);
const REVIEW_BY = new Date(Date.parse(`${TODAY}T00:00:00Z`) + 89 * 86400000).toISOString().slice(0, 10);
const errors = [];
const fail = (q, msg) => errors.push(`${q.key}: ${msg}`);
const list = xs => xs.length <= 1 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`;
const fill = (tpl, vars, q) => tpl.replace(/\{(\w+)\}/g, (_, k) => {
  if (vars[k] === undefined) { fail(q, `explanation placeholder {${k}} has no value`); return ''; }
  return vars[k];
});

// ---------- formatting (display copy) ----------
function people(v) {
  if (v >= 1e9) return `${(v / 1e9).toFixed(2).replace(/0$/, '')} billion`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(v >= 1e8 ? 0 : 1).replace(/\.0$/, '')} million`;
  return `${Math.round(v / 1e3).toLocaleString('en-US')},000`;
}
function km2(v) {
  if (v >= 1e6) return `${(v / 1e6).toFixed(2).replace(/0$/, '')} million km²`;
  const sig = v >= 1e5 ? 1e3 : 1e2;
  return `${(Math.round(v / sig) * sig).toLocaleString('en-US')} km²`;
}
const fmtMetric = (metric, v) => metric === 'population' ? people(v) : km2(v);
const the = id => ['NLD', 'GBR', 'USA', 'PHL', 'ARE', 'CAF', 'COG', 'COD', 'DOM', 'BHS', 'GMB', 'MDV', 'MHL', 'SLB', 'CZE'].includes(id) ? 'the ' : '';
const display = id => DISPLAY_NAMES[id] ?? name(id);
const theName = id => the(id) + display(id);
const cap = s => s[0].toUpperCase() + s.slice(1);

// ---------- sources ----------
const factbookUrl = id => {
  const f = snap.facts.scalar.find(x => x.subjectId === id && /factbook\.json\/blob/.test(x.sourceUrl));
  return f ? f.sourceUrl.replace(/\/blob\//, '/blob/') : `https://github.com/factbook/factbook.json/tree/${snap.references.factbookCommit}`;
};
const SRC = {
  factbook: id => ({title: `CIA World Factbook, final edition (pinned mirror) — ${display(id)}`, url: factbookUrl(id), retrieved: snap.references.factbookRetrieved}),
  wb: (id, ind) => ({title: `World Bank WDI ${ind} — ${display(id)} (${snap.wb[id][ind].year})`, url: `https://api.worldbank.org/v2/country/${id}/indicator/${ind}?format=json&mrnev=1`, retrieved: snap.references.worldBankRetrieved}),
  m49: {title: 'UN M49 standard country and area codes (continent grouping used by Scalar)', url: 'https://unstats.un.org/unsd/methodology/m49/', retrieved: TODAY},
  ne: {title: 'Natural Earth admin-0 country boundaries (geometry used by Tectonic)', url: 'https://www.naturalearthdata.com/downloads/', retrieved: TODAY},
  fact: f => ({title: f.sourceTitle, url: f.sourceUrl, retrieved: f.reviewedAt}),
};
const gameRef = path => `scalargame@${snap.manifest.commit.slice(0, 7)}:${path}`;

// ---------- reviewed facts must match the snapshot content they were reviewed against ----------
function canonicalJson(v) {
  if (Array.isArray(v)) return `[${v.map(canonicalJson).join(',')}]`;
  if (v && typeof v === 'object') return `{${Object.keys(v).filter(k => k !== 'runtimeFingerprint' && v[k] !== undefined).sort().map(k => `${JSON.stringify(k)}:${canonicalJson(v[k])}`).join(',')}}`;
  return JSON.stringify(v);
}
const fp = v => createHash('sha256').update(canonicalJson(v)).digest('hex');
const eventIndex = new Map();
for (const p of snap.puzzles) for (const e of p.events) {
  const rec = eventIndex.get(String(e.id)) ?? {event: e, dates: [], fingerprints: new Set()};
  rec.dates.push(p.playDate); rec.fingerprints.add(fp(e)); eventIndex.set(String(e.id), rec);
}

// Questions already published from the 2026-10-05 legacy batch (ep01–ep08, see out/social-site/catalog.json).
// A new question may not reuse the same game + subject; the Pi only knows these by their old ep IDs. This list is
// permanent (it applies to every batch); later batches are covered by libraryEpisodes() below.
const LEGACY = {'scalar:BOL': 'ep01', 'scalar:NPL': 'ep02', 'continuum:JPN-MEX': 'ep03', 'continuum:MEX-JPN': 'ep03', 'continuum:ARG-KAZ': 'ep04', 'continuum:KAZ-ARG': 'ep04',
  'whenabouts:158': 'ep05', 'whenabouts:978': 'ep05', 'whenabouts:935': 'ep06', 'tectonic:MNG': 'ep07', 'tectonic:VNM': 'ep08'};
const withExtra = (q, sources) => [...sources, ...(q.extraSources ?? [])];
const resolved = [];
const usedSubjects = new Map();
const noteSubject = (q, id) => { if (q.spare) return; const k = `${q.game}:${id}`; usedSubjects.set(k, [...(usedSubjects.get(k) ?? []), q.key]); };

for (const q of QUESTIONS) {
  const out = {key: q.key, game: q.game, format: q.format, difficulty: q.difficulty, pilot: !!q.pilot, spare: !!q.spare, rationale: q.rationale,
    destination: {game: q.game, deepLink: `/${q.game}`}, reviewBy: REVIEW_BY};
  if (q.game === 'scalar') {
    const a = S.byId[q.answer];
    if (!a) { fail(q, 'unknown answer'); continue; }
    if (SENSITIVE.has(a.id)) fail(q, 'answer on SENSITIVE list');
    if (picks.has(a.id)) fail(q, `answer is a Scalar Daily pick on ${picks.get(a.id)}`);
    const preds = q.clues.map(id => S.pById[id] ?? (fail(q, `unknown clue ${id}`), null)).filter(Boolean);
    for (const p of preds) if (!S.strictly(a, p)) fail(q, `answer does not strictly satisfy "${p.text}" (or is ambiguous within ${MARGIN * 100}%)`);
    if (new Set(preds.map(p => p.field)).size !== preds.length) fail(q, 'two clues test the same field');
    const choiceIds = q.format === 'progressive-clues' ? q.choices : q.candidates;
    if (choiceIds.filter(c => c === a.id).length !== 1 || new Set(choiceIds).size !== 3) fail(q, 'choices must be 3 distinct with the answer once');
    for (const c of choiceIds) if (SENSITIVE.has(c)) fail(q, `choice ${c} is SENSITIVE`);
    for (const d of choiceIds.filter(c => c !== a.id)) if (!preds.some(p => p.test(S.byId[d]) === false)) fail(q, `decoy ${d} is not definitely eliminated by any clue`);
    // Candidate counts across the full 195-country universe.
    let set = snap.countries; const counts = [];
    for (const p of preds) { set = set.filter(c => S.possible(c, p)); counts.push(set.length); }
    if (q.format === 'progressive-clues' && (counts.at(-1) !== 1 || set[0].id !== a.id)) fail(q, `final clue set matches ${counts.at(-1)} countries: ${set.map(c => c.id)}`);
    const borders = [...S.fbBorders(a.id)].map(display).sort();
    const pop = snap.wb[a.id]['SP.POP.TOTL'], area = snap.wb[a.id]['AG.SRF.TOTL.K2'];
    const vars = {name: display(a.id), borders: list(borders), pop: people(pop.value), area: km2(area.value), count1: counts[0], count2: counts[1]};
    let elimination = null;
    if (q.format === 'candidate-elimination') {
      // Apply clues in order: each must remove at least one remaining candidate; one survivor at the end.
      let alive = [...choiceIds]; elimination = [];
      for (const p of preds) {
        const removed = alive.filter(c => p.test(S.byId[c]) === false);
        if (alive.some(c => p.test(S.byId[c]) === null)) fail(q, `"${p.text}" is ambiguous for a remaining candidate`);
        alive = alive.filter(c => !removed.includes(c));
        elimination.push(removed);
      }
      if (alive.length !== 1 || alive[0] !== a.id) fail(q, `elimination leaves ${alive}`);
      if (elimination.filter(r => r.length).length < 2) fail(q, 'fewer than two clues eliminate anyone');
      const named = elimination.flat();
      Object.assign(vars, {elim1: display(named[0]), elim2: display(named[1])});
    }
    // Hand-written claims in an explanation must be backed by an assertion proven here.
    for (const [subject, pred, expect] of q.asserts ?? []) {
      if (subject === 'neighborsAllLandlocked') {
        const bad = [...S.fbBorders(a.id)].filter(n => snap.factbook[n]?.landlocked !== 'true');
        if (bad.length) fail(q, `neighbors not landlocked: ${bad}`);
      } else if (S.pById[pred].test(S.byId[subject]) !== expect) fail(q, `assert ${subject} ${pred} = ${expect} failed`);
    }
    const fields = new Set(preds.map(p => p.field));
    const sources = [];
    if (fields.has('continent')) sources.push(SRC.m49);
    if ([...fields].some(f => ['is_landlocked', 'border_countries_count', 'government_type'].includes(f))) sources.push(SRC.factbook(a.id));
    if (fields.has('population') || /\{pop\}/.test(q.explanation)) sources.push(SRC.wb(a.id, 'SP.POP.TOTL'));
    if (fields.has('area') || /\{area\}/.test(q.explanation)) sources.push(SRC.wb(a.id, 'AG.SRF.TOTL.K2'));
    if (/\{borders\}/.test(q.explanation) && !sources.some(s => s.url === factbookUrl(a.id))) sources.push(SRC.factbook(a.id));
    const letters = ['A', 'B', 'C'];
    Object.assign(out, {
      subjectId: a.id, questionId: `scalar:${a.id}:${q.format === 'progressive-clues' ? 'clues' : 'elimination'}`,
      hook: q.format === 'progressive-clues' ? 'Three clues. One country.' : 'Only one of these fits every clue.',
      question: q.format === 'progressive-clues' ? 'Which country?' : 'Which country fits all three clues?',
      clues: preds.map(p => p.text), clueIds: q.clues,
      choices: choiceIds.map((c, i) => ({key: letters[i], label: display(c), id: c})),
      answer: display(a.id), answerKey: letters[choiceIds.indexOf(a.id)], answerAliases: [a.id, ...(a.name !== display(a.id) ? [a.name] : [])],
      explanation: fill(q.explanation, vars, q),
      evidence: {sources, checks: {uniqueAnswer: true, candidateCounts: counts, universe: snap.countries.length, numericMargin: MARGIN,
        ...(elimination ? {eliminatedPerClue: elimination} : {}), scalarDailyPickWindow: `${TODAY}+90d clear`},
        values: {population: pop, area}, gameData: gameRef('src/scalar/assets/data/gameData.json'), reviewer: null},
    });
    noteSubject(q, a.id);
  }

  if (q.game === 'continuum') {
    const ind = q.metric === 'population' ? 'SP.POP.TOTL' : 'AG.SRF.TOTL.K2';
    const MIN = q.metric === 'population' ? 1.15 : 1.1;
    const ids = q.format === 'head-to-head' ? q.choices : [q.anchors[0], q.target, q.anchors[1]];
    for (const id of ids) if (SENSITIVE.has(id)) fail(q, `${id} is SENSITIVE`);
    for (const id of ids) if (S.defect(S.byId[id], q.metric)) fail(q, `${id} ${q.metric} is a documented data defect`);
    const ref = Object.fromEntries(ids.map(id => [id, snap.wb[id]?.[ind]]));
    const game = Object.fromEntries(ids.map(id => [id, S.byId[id]?.[q.metric]]));
    if (ids.some(id => !ref[id] || !Number.isFinite(game[id]))) { fail(q, 'missing value'); continue; }
    const years = new Set(ids.map(id => ref[id].year));
    if (years.size !== 1) fail(q, `mixed reference years ${[...years]}`);
    const order = src => [...ids].sort((x, y) => src[x] - src[y]);
    const refVal = Object.fromEntries(ids.map(id => [id, ref[id].value]));
    if (order(refVal).join() !== order(game).join()) fail(q, 'game data and World Bank reference disagree on order');
    const sorted = order(refVal);
    for (let i = 1; i < sorted.length; i++) {
      const r = refVal[sorted[i]] / refVal[sorted[i - 1]], g = game[sorted[i]] / game[sorted[i - 1]];
      if (r < MIN) fail(q, `${sorted[i - 1]}→${sorted[i]} reference ratio ${r.toFixed(3)} below ${MIN}`);
      if (g < 1.05) fail(q, `${sorted[i - 1]}→${sorted[i]} game-data ratio ${g.toFixed(3)} below 1.05`);
    }
    const year = [...years][0];
    const sources = ids.map(id => SRC.wb(id, ind));
    const label = q.metric === 'population' ? 'people' : 'area';
    const valueText = Object.fromEntries(ids.map(id => [id, fmtMetric(q.metric, refVal[id])]));
    if (q.format === 'head-to-head') {
      const [x, y] = q.choices, winner = refVal[x] > refVal[y] ? x : y, loser = winner === x ? y : x;
      const otherInd = ind === 'SP.POP.TOTL' ? 'AG.SRF.TOTL.K2' : 'SP.POP.TOTL';
      const otherRatio = snap.wb[loser][otherInd].value / snap.wb[winner][otherInd].value;
      const vars = {winner: display(winner), loser: display(loser), winnerValue: valueText[winner], loserValue: valueText[loser], year,
        otherRatio: otherRatio >= 1.5 ? (Math.round(otherRatio * 10) / 10).toString().replace(/\.0$/, '') : undefined};
      if (/\{otherRatio\}/.test(q.explanation)) sources.push(...[winner, loser].map(id => SRC.wb(id, otherInd)));
      Object.assign(out, {
        subjectId: `${x}-${y}`, questionId: `continuum:${q.metric}:${[x, y].sort().join('-')}:head-to-head`,
        hook: q.metric === 'population' ? 'Which has more people?' : 'Which is bigger?',
        question: q.metric === 'population' ? `More people: ${theName(x)} or ${theName(y)}?` : `Larger area: ${theName(x)} or ${theName(y)}?`,
        choices: [x, y].map((id, i) => ({key: 'AB'[i], label: display(id), id})),
        answer: display(winner), answerKey: 'AB'[[x, y].indexOf(winner)], answerAliases: [winner],
        explanation: fill(q.explanation, vars, q),
        metric: {id: q.metric, label, definition: q.metric === 'population' ? 'Total population (World Bank estimate)' : 'Total area: land plus inland water (World Bank)', year, unit: q.metric === 'population' ? 'people' : 'km²'},
        values: ids.map(id => ({id, label: display(id), value: refVal[id], text: valueText[id]})),
        evidence: {sources, checks: {uniqueAnswer: true, ratio: +(refVal[winner] / refVal[loser]).toFixed(3), gameDataAgrees: true, minRatio: MIN, referenceYear: year},
          gameData: gameRef('src/scalar/assets/data/continuumGameData.json'), reviewer: null},
      });
      ids.forEach(id => noteSubject(q, id));
    } else {
      const [lo, hi] = q.anchors, t = q.target;
      if (refVal[lo] >= refVal[hi]) fail(q, 'anchors must be listed low → high');
      const slot = refVal[t] < refVal[lo] ? 0 : refVal[t] > refVal[hi] ? 2 : 1;
      const less = q.metric === 'population' ? 'Fewer people than' : 'Smaller than', more = q.metric === 'population' ? 'More people than' : 'Larger than';
      const choices = [
        {key: 'A', label: `${less} ${theName(lo)}`, poll: `Below ${display(lo)}`},
        {key: 'B', label: `Between ${theName(lo)} and ${theName(hi)}`, poll: `Between`},
        {key: 'C', label: `${more} ${theName(hi)}`, poll: `Above ${display(hi)}`},
      ];
      for (const c of choices) if (c.poll.length > 25) fail(q, `poll option too long: ${c.poll}`);
      const vars = {low: display(lo), high: display(hi), target: display(t), lowValue: valueText[lo], highValue: valueText[hi], targetValue: valueText[t], year,
        ordered: sorted.map(id => `${display(id)} ${valueText[id]}`).join(' < ')};
      Object.assign(out, {
        subjectId: t, questionId: `continuum:${q.metric}:${t}:missing-slot:${[lo, hi].join('-')}`,
        hook: 'Where does it fit?',
        question: q.metric === 'population' ? `Ranked by population, where does ${theName(t)} go?` : `Ranked by area, where does ${theName(t)} go?`,
        anchors: [lo, hi].map(id => ({id, label: display(id), value: refVal[id], text: valueText[id]})),
        target: {id: t, label: display(t), value: refVal[t], text: valueText[t]},
        choices, answer: choices[slot].poll, answerKey: choices[slot].key, answerAliases: [],
        explanation: fill(q.explanation, vars, q),
        metric: {id: q.metric, label, definition: q.metric === 'population' ? 'Total population (World Bank estimate)' : 'Total area: land plus inland water (World Bank)', year, unit: q.metric === 'population' ? 'people' : 'km²'},
        values: sorted.map(id => ({id, label: display(id), value: refVal[id], text: valueText[id]})),
        evidence: {sources, checks: {uniqueAnswer: true, slot: ['below', 'between', 'above'][slot], adjacentRatios: sorted.slice(1).map((id, i) => +(refVal[id] / refVal[sorted[i]]).toFixed(3)), gameDataAgrees: true, minRatio: MIN, referenceYear: year},
          gameData: gameRef('src/scalar/assets/data/continuumGameData.json'), reviewer: null},
      });
      noteSubject(q, t);
    }
  }

  if (q.game === 'whenabouts') {
    const recs = [q.event, q.anchor].filter(Boolean).map(id => eventIndex.get(id));
    if (recs.some(r => !r)) { fail(q, 'unknown event'); continue; }
    for (const r of recs) {
      if (WHENABOUTS_FRESHNESS === 'strict' && !r.dates.every(d => d <= LATEST)) fail(q, `event ${r.event.id} appears in a Daily after ${LATEST}: ${r.dates.filter(d => d > LATEST)}`);
      if (r.fingerprints.size !== 1) fail(q, `event ${r.event.id} content differs between Daily appearances`);
      if (/\b\d{3,4}\b/.test(r.event.title)) fail(q, `title leaks a number: ${r.event.title}`);
    }
    const factFor = r => snap.facts.whenabouts.find(f => String(f.subjectId) === String(r.event.id) && f.contentFingerprint === [...r.fingerprints][0]);
    const facts = recs.map(factFor);
    if (facts.some(f => !f)) fail(q, 'no reviewed fact bound to this exact event content');
    const e = recs[0].event;
    const dateText = ev => (ev.month && ev.day) ? `${new Date(Date.UTC(2000, ev.month - 1, ev.day)).toLocaleDateString('en-US', {month: 'long', day: 'numeric', timeZone: 'UTC'})}, ${yearLabel(ev.year)}` : yearLabel(ev.year);
    const precise = !!(e.month && e.day);
    const sources = facts.filter(Boolean).map(SRC.fact);
    if (q.format === 'guess-the-year') {
      const ys = q.choiceYears;
      if (ys.filter(y => y === e.year).length !== 1 || new Set(ys).size !== 3 || [...ys].sort((a, b) => a - b).join() !== ys.join()) fail(q, 'year choices must be 3 ascending, distinct, answer once');
      const minGap = Math.min(...ys.slice(1).map((y, i) => Math.abs(yearsBetween(ys[i], y))));
      if (!e.month) fail(q, 'guess-the-year requires at least a month-precise event date in the source data');
      const vars = {date: dateText(e), fact: facts[0]?.text ?? ''};
      Object.assign(out, {
        subjectId: e.id, questionId: `whenabouts:${e.id}:guess-the-year`,
        hook: 'Guess the year.', question: `${q.prompt}. What year?`, prompt: q.prompt,
        choices: ys.map((y, i) => ({key: 'ABC'[i], label: yearLabel(y), year: y})),
        answer: yearLabel(e.year), answerKey: 'ABC'[ys.indexOf(e.year)], answerAliases: [String(e.year)],
        explanation: fill(q.explanation, vars, q), event: {id: e.id, title: e.title, year: e.year, month: e.month, day: e.day},
        evidence: {sources, checks: {uniqueAnswer: true, choiceSpacingYears: minGap, dailyAppearances: recs[0].dates, futureDailyAppearances: recs[0].dates.filter(d => d > LATEST).length, freshnessRule: WHENABOUTS_FRESHNESS, factFingerprintMatches: !!facts[0]},
          gameData: gameRef('public/puzzles'), reviewer: null},
      });
    } else {
      const an = recs[1].event;
      const gap = Math.abs(yearsBetween(Math.min(e.year, an.year), Math.max(e.year, an.year)));
      // Modern events with day-precise dates in both records may be close; otherwise require a margin over dating uncertainty.
      const precisePair = !!(e.month && e.day && an.month && an.day);
      const minGap = Math.min(e.year, an.year) >= 1500 ? (precisePair ? 1 : 5) : 100;
      if (gap < minGap) fail(q, `gap ${gap} years below ${minGap}`);
      for (const [k, v] of q.asserts ?? []) if (k === 'gapYears' && gap !== v) fail(q, `assert gapYears ${v} failed (${gap})`);
      const after = e.year > an.year || (e.year === an.year && (e.month ?? 0) > (an.month ?? 0));
      const vars = {title: e.title, year: yearLabel(e.year), anchorTitle: an.title, anchorYear: yearLabel(an.year), gap, date: dateText(e), anchorDate: dateText(an)};
      Object.assign(out, {
        subjectId: `${e.id}-${an.id}`, questionId: `whenabouts:${e.id}:before-after:${an.id}`,
        hook: 'Before or after?', question: `Before or after ${q.anchorPrompt}?`, prompt: q.prompt, anchorPrompt: q.anchorPrompt,
        choices: [{key: 'A', label: 'Before'}, {key: 'B', label: 'After'}],
        answer: after ? 'After' : 'Before', answerKey: after ? 'B' : 'A', answerAliases: [],
        explanation: fill(q.explanation, vars, q),
        event: {id: e.id, title: e.title, year: e.year, month: e.month, day: e.day}, anchor: {id: an.id, title: an.title, year: an.year, month: an.month, day: an.day},
        evidence: {sources, checks: {uniqueAnswer: true, gapYears: gap, minGapYears: minGap, precisePair, futureDailyAppearances: Object.fromEntries(recs.map(r => [r.event.id, r.dates.filter(d => d > LATEST).length])), freshnessRule: WHENABOUTS_FRESHNESS, factFingerprintMatches: facts.every(Boolean)},
          gameData: gameRef('public/puzzles'), reviewer: null},
        sensitiveReview: q.sensitiveReview ?? null,
      });
    }
    recs.forEach(r => noteSubject(q, r.event.id));
  }

  if (q.game === 'tectonic') {
    const t = S.globeById[q.answer];
    if (!t) { fail(q, 'answer missing from globe'); continue; }
    const land = id => [...S.fbBorders(id)].filter(n => S.globeById[n]); // Factbook land borders present on the globe
    const ln = land(t.id);
    const drawn = new Set([t.id, ...ln, ...ln.flatMap(land)]);
    for (const id of [t.id, ...ln]) if (CONTESTED_MAP.has(id)) fail(q, `target/neighbor ${id} is contested or sensitive`);
    for (const id of drawn) if (CONTESTED.has(id)) fail(q, `frame would draw contested ${id}`);
    for (const c of q.choices) if (CONTESTED_MAP.has(c)) fail(q, `choice ${c} contested/sensitive`);
    if (q.choices.filter(c => c === t.id).length !== 1 || new Set(q.choices).size !== 3) fail(q, 'choices must be 3 distinct with the answer once');
    const sources = [SRC.ne, SRC.factbook(t.id)];
    if (q.format === 'neighbor-clues') {
      const universe = snap.globe.map(g => g.id);
      for (const s of q.shown) if (!ln.includes(s) || !S.globeById[t.id].neighbors.includes(s)) fail(q, `${s} is not a land neighbor in both Factbook and globe adjacency`);
      const matches = universe.filter(u => q.shown.every(s => land(u).includes(s)));
      if (matches.length !== 1 || matches[0] !== t.id) fail(q, `shown neighbors match ${matches}`);
      const all = q.shown.length === ln.length;
      if (/all of/.test(q.explanation) && !all) fail(q, 'explanation claims all neighbors but the list is partial');
      const counts = q.shown.map((_, i) => universe.filter(u => q.shown.slice(0, i + 1).every(s => land(u).includes(s))).length);
      for (const d of q.choices.filter(c => c !== t.id)) if (q.shown.every(s => land(d).includes(s))) fail(q, `decoy ${d} also borders all shown`);
      Object.assign(out, {
        subjectId: t.id, questionId: `tectonic:${t.id}:neighbor-clues`,
        hook: all ? 'These are all its land neighbors.' : 'It borders all three of these.',
        question: 'Which country is it?', shown: q.shown.map(id => ({id, label: display(id)})), allNeighbors: all,
        choices: q.choices.map((c, i) => ({key: 'ABC'[i], label: display(c), id: c})),
        answer: display(t.id), answerKey: 'ABC'[q.choices.indexOf(t.id)], answerAliases: [t.id, ...(t.name !== display(t.id) ? [t.name] : [])],
        explanation: fill(q.explanation, {name: display(t.id), shown: list(q.shown.map(theName)), neighbors: list(ln.map(theName).sort())}, q),
        geometry: {target: t.id, neighbors: ln, frame: [...drawn]},
        evidence: {sources: [...sources, ...q.shown.map(SRC.factbook)], checks: {uniqueAnswer: true, candidateCounts: counts, landNeighbors: ln, allNeighborsShown: all, adjacencyAgreesWithGlobe: true},
          gameData: gameRef('public/tectonic/globe/countries.json'), reviewer: null},
      });
    } else {
      if (ln.length < 2) fail(q, 'gap needs at least two land neighbors');
      const [lon, lat] = t.centroid, k = Math.cos(lat * Math.PI / 180);
      const span = Math.max(8, 2.6 * Math.max((t.bbox[2] - t.bbox[0]) * k, t.bbox[3] - t.bbox[1]));
      const frameBbox = [lon - span / 2 / k, lat - span / 2, lon + span / 2 / k, lat + span / 2].map(v => +v.toFixed(3));
      // A country is in the window if any of its polygon vertices falls inside it (bboxes break at the antimeridian).
      const hits = g => g.rings.some(r => r.some(([x, y]) => x >= frameBbox[0] && x <= frameBbox[2] && y >= frameBbox[1] && y <= frameBbox[3]));
      const inFrame = snap.globe.filter(hits).map(g => g.id);
      for (const id of inFrame) if (CONTESTED.has(id)) fail(q, `map window shows contested ${id}`);
      for (const d of q.choices.filter(c => c !== t.id)) if (inFrame.includes(d)) fail(q, `decoy ${d} is drawn in the map window`);
      drawn.clear(); inFrame.forEach(id => drawn.add(id));
      Object.assign(out, {
        subjectId: t.id, questionId: `tectonic:${t.id}:missing-country`,
        hook: 'One country is missing.', question: 'Which country fills the gap?',
        choices: q.choices.map((c, i) => ({key: 'ABC'[i], label: display(c), id: c})),
        answer: display(t.id), answerKey: 'ABC'[q.choices.indexOf(t.id)], answerAliases: [t.id, ...(t.name !== display(t.id) ? [t.name] : [])],
        explanation: fill(q.explanation, {name: display(t.id), neighbors: list(ln.map(theName).sort())}, q),
        geometry: {target: t.id, neighbors: ln, frame: [...drawn], frameBbox},
        evidence: {sources, checks: {uniqueAnswer: true, landNeighbors: ln, gapEnclosedBy: ln.length, adjacencyAgreesWithGlobe: ln.every(n => t.neighbors.includes(n))},
          gameData: gameRef('public/tectonic/globe/countries.json'), reviewer: null},
      });
    }
    noteSubject(q, t.id);
  }
  // Spoiler self-check on the displayed question side (choices excluded: they contain the answer by design).
  for (const subj of String(out.subjectId ?? '').split(/(?<=^\d+)-|(?<=^[A-Z]{3})-(?=[A-Z]{3}$)/).concat(out.subjectId)) {
    const hit = LEGACY[`${q.game}:${subj}`]; if (hit) fail(q, `repeats legacy published question ${hit}`);
  }
  if (out.evidence) out.evidence.sources = withExtra(q, out.evidence.sources);
  if (q.note) out.editorialNote = q.note;
  // Head-to-head names both choices in the question by design; before-after/missing-slot answers are choice words.
  const pre = [out.hook, out.question, ...(out.clues ?? []), out.prompt ?? '', out.anchorPrompt ?? ''].join(' ').toLowerCase();
  const word = a => new RegExp(`(^|[^\\p{L}])${a.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^\\p{L}]|$)`, 'u');
  if (!['before-after', 'missing-slot', 'head-to-head'].includes(q.format) && [out.answer, ...out.answerAliases].some(a => a && word(a).test(pre))) fail(q, 'answer appears in pre-reveal text');
  resolved.push(out);
}

for (const [k, keys] of usedSubjects) if (keys.length > 1) errors.push(`repeat: ${k} used by ${keys.join(', ')}`);
const main = resolved.filter(r => !r.spare);

// ---------- batch rules from CONFIG ----------
const games = ['scalar', 'continuum', 'whenabouts', 'tectonic'];
const scopeFormats = Object.keys(CONFIG.scope);
for (const g of games) {
  const mine = main.filter(r => r.game === g);
  for (const fm of [...new Set(mine.map(r => r.format))]) if (!scopeFormats.includes(`${g}/${fm}`)) errors.push(`${g}/${fm}: not in CONFIG.scope`);
  for (const [unit, want] of Object.entries(CONFIG.mix ?? {}).filter(([u]) => u === g || u.startsWith(`${g}/`))) {
    const rows = unit === g ? mine : mine.filter(r => `${g}/${r.format}` === unit);
    const mix = DIFFICULTIES.map(d => rows.filter(r => r.difficulty === d).length).join('/');
    if (mix !== want.join('/')) errors.push(`${unit}: difficulty mix ${mix}, need ${want.join('/')}`);
  }
  const inScope = scopeFormats.some(u => u.startsWith(`${g}/`));
  if (inScope && mine.filter(r => r.pilot).length !== (CONFIG.pilotsPerGame ?? 0)) errors.push(`${g}: needs exactly ${CONFIG.pilotsPerGame ?? 0} pilot(s)`);
  if (!inScope && mine.some(r => r.pilot)) errors.push(`${g}: pilot outside CONFIG.scope`);
  const fmts = [...new Set(mine.map(r => r.format))];
  // Viewers see many episodes: the correct letter must not be the same for every episode of a format.
  for (const fm of fmts) { const ks = mine.filter(r => r.format === fm).map(r => r.answerKey); if (ks.length > 1 && new Set(ks).size < 2) errors.push(`${g}/${fm}: every answer is ${ks[0]}`); }
}
for (const [unit, want] of Object.entries(CONFIG.scope)) {
  const have = main.filter(r => `${r.game}/${r.format}` === unit).length;
  if (have !== want) errors.push(`${unit.split('/')[0]}: format ${unit.split('/')[1]} needs ${want} episode${want === 1 ? '' : 's'} (has ${have})`);
}

// ---------- episode IDs and repeats against the whole library ----------
// Every main question needs a permanent ID in CONFIG.episodes; a questionId or episode ID already used by another
// episode in any library/<batch>/ (batch.json or frozen job input) is refused. Spares never get an ID.
const known = libraryEpisodes();
const allocated = Object.values(CONFIG.episodes).map(([, id]) => id);
const suggest = [];
for (const r of resolved) {
  const ep = CONFIG.episodes[r.key];
  if (r.spare) { if (ep) errors.push(`${r.key}: spare has an episode ID in CONFIG.episodes`); }
  else if (!ep) {
    const id = nextEpisodeId(`${r.game}-${FORMAT_SHORT[r.format]}`, [...allocated, ...suggest.map(s => s[1])]);
    suggest.push([r.key, id]);
    errors.push(`${r.key}: no episode ID in CONFIG.episodes (next free: '${r.key}': ['${CONFIG.batches.at(-1)}', '${id}'])`);
  } else {
    const [b, id] = ep;
    if (!CONFIG.batches.includes(b)) errors.push(`${r.key}: episode batch ${b} not in CONFIG.batches`);
    if (!new RegExp(`^${r.game}-${FORMAT_SHORT[r.format]}-\\d{3}$`).test(id)) errors.push(`${r.key}: episode ID ${id} must be ${r.game}-${FORMAT_SHORT[r.format]}-<nnn>`);
    if (allocated.filter(x => x === id).length > 1) errors.push(`${r.key}: episode ID ${id} allocated twice in CONFIG.episodes`);
    for (const e of known.filter(e => e.episodeId === id && e.questionId !== r.questionId)) errors.push(`${r.key}: episode ID ${id} is already ${e.questionId} in ${e.batchId}`);
  }
  for (const e of known.filter(e => e.questionId === r.questionId && e.episodeId !== ep?.[1])) errors.push(`${r.key}: questionId ${r.questionId} already used by ${e.episodeId} in ${e.batchId}`);
}
for (const key of Object.keys(CONFIG.episodes)) if (!resolved.some(r => r.key === key)) errors.push(`CONFIG.episodes: ${key} is not a question in this set`);
// Same subject in an earlier batch (different question): allowed, but say so for the pack review.
const earlierSubjects = new Map(known.filter(e => !CONFIG.batches.includes(e.batchId)).flatMap(e => subjectsOf(e.questionId).map(s => [s, e.episodeId])));
for (const r of main) for (const s of subjectsOf(r.questionId)) if (earlierSubjects.has(s)) console.error(`note: ${r.key} reuses subject ${s} (also in ${earlierSubjects.get(s)})`);
/** game:subject keys of a questionId (both countries of a head-to-head, both events of a before-after). */
function subjectsOf(qid) {
  const p = qid.split(':');
  if (p[0] === 'continuum') return (p[3] === 'head-to-head' ? p[2].split('-') : [p[2]]).map(x => `continuum:${x}`);
  if (p[0] === 'whenabouts' && p[2] === 'before-after') return [`whenabouts:${p[1]}`, `whenabouts:${p[3]}`];
  return [`${p[0]}:${p[1]}`];
}

if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
const doc = {set: SET.name, snapshotId: SNAPSHOT, snapshotHash: snap.manifest.snapshotHash, gameCommit: snap.manifest.commit, checkedFor: TODAY,
  latestEndedDate: LATEST, reviewBy: REVIEW_BY, questions: resolved};
doc.questionsHash = createHash('sha256').update(JSON.stringify(resolved)).digest('hex');
const outPath = SET.checkedPath;
mkdirSync(SET.outDir, {recursive: true});
const text = JSON.stringify(doc, null, 2) + '\n';
if (!existsSync(outPath) || readFileSync(outPath, 'utf8') !== text) writeFileSync(outPath, text); // identical: leave the file untouched
console.log(JSON.stringify({ok: true, questions: resolved.length, main: main.length, spares: resolved.length - main.length, out: outPath, questionsHash: doc.questionsHash}, null, 1));
