// Enumerate checked candidate questions for all eight formats from a frozen snapshot.
//   node studio/pipeline/candidates.mjs --snapshot=<snapshotId> [--today=YYYY-MM-DD] [--out=<file.json>]
// Writes library/_sources/<snapshot>/candidates.json (or --out). It refuses to replace an existing, different
// candidates.json in a snapshot folder (tracked evidence): use --out, e.g. CONFIG.outDir of a set. Every candidate carries the deterministic
// checks it passed; editorial selection happens in questions-<batch>.mjs, which re-runs these checks.
import {writeFileSync, existsSync, readFileSync, mkdirSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {ROOT, loadSnapshot, buildScalar, MARGIN, SENSITIVE, CONTESTED_MAP, safeLatest, upcomingScalarPicks, yearsBetween} from './lib.mjs';

const args = Object.fromEntries(process.argv.slice(2).map(a => a.replace(/^--/, '').split('=')));
if (!args.snapshot) throw new Error('--snapshot=<snapshotId> required');
const snap = loadSnapshot(args.snapshot);
const TODAY = args.today ?? new Date().toISOString().slice(0, 10);
const PICK_WINDOW_DAYS = 90;

// ---------- Scalar ----------
const {P, refDisagreements, usable, possible, strictly, byId, globeById, fbBorders, defect} = buildScalar(snap);

const picks = await upcomingScalarPicks(snap, TODAY, PICK_WINDOW_DAYS);
const answerable = snap.countries.filter(c => !SENSITIVE.has(c.id) && !picks.has(c.id));

function scalarClues() {
  const out = [];
  const broad = usable.filter(p => p.kind === 'broad'), rest = usable.filter(p => p.kind !== 'broad');
  for (const a of answerable) for (const p1 of broad) {
    if (!strictly(a, p1)) continue;
    const s1 = snap.countries.filter(c => possible(c, p1));
    if (s1.length < 8) continue;
    for (const p2 of rest) {
      if (p2 === p1 || p2.field === p1.field || !strictly(a, p2)) continue;
      const s2 = s1.filter(c => possible(c, p2));
      if (s2.length < 2 || s2.length > 12) continue;
      for (const p3 of rest) {
        if ([p1.field, p2.field].includes(p3.field) || !strictly(a, p3)) continue;
        const s3 = s2.filter(c => possible(c, p3));
        if (s3.length !== 1 || s3[0].id !== a.id) continue;
        const decoys = s2.filter(c => c.id !== a.id && !SENSITIVE.has(c.id)).map(c => c.id);
        if (decoys.length < 2) continue;
        out.push({format: 'progressive-clues', answer: a.id, name: a.name, clues: [p1.id, p2.id, p3.id], candidateCounts: [s1.length, s2.length, 1],
          letterClue: p3.kind === 'letter', decoyPool: decoys});
      }
    }
  }
  return out;
}

function scalarElimination() {
  const out = [];
  const preds = usable.filter(p => p.kind === 'filter' || p.id === 'landlocked' || p.id === 'coastal' || p.id === 'island');
  for (const a of answerable) {
    const peers = snap.countries.filter(c => c.id !== a.id && c.continent === a.continent && !SENSITIVE.has(c.id)
      && (c.subregion === a.subregion || Math.max(c.population, a.population) / Math.min(c.population, a.population) < 3));
    const truths = preds.filter(p => strictly(a, p));
    const mine = [];
    for (let i = 0; i < peers.length; i++) for (let j = i + 1; j < peers.length; j++) {
      const [b, c] = [peers[i], peers[j]];
      // Three clues, applied in order. Clue 1 eliminates exactly one decoy, clue 2 the other, clue 3 rules out nobody
      // new but must be true of the answer and false for at least one decoy (so the reveal teaches all three).
      for (const p1 of truths) {
        const f1 = [b, c].filter(x => p1.test(x) === false);
        if (f1.length !== 1) continue;
        const left = [b, c].find(x => p1.test(x) !== false);
        for (const p2 of truths) {
          if (p2.field === p1.field || p2.test(left) !== false) continue;
          for (const p3 of truths) {
            if ([p1.field, p2.field].includes(p3.field)) continue;
            if (![b, c].some(x => p3.test(x) === false)) continue;
            if ([b, c].some(x => p1.test(x) === null || p2.test(x) === null || p3.test(x) === null)) continue;
            const sameSub = [b, c].filter(x => x.subregion === a.subregion).length;
            mine.push({format: 'candidate-elimination', answer: a.id, name: a.name, candidates: [a.id, b.id, c.id], clues: [p1.id, p2.id, p3.id],
              eliminations: [f1[0].id, left.id], plausibility: sameSub});
          }
        }
      }
    }
    // Keep a handful per answer: most plausible decoys first, distinct decoy pairs and clue sets.
    const seen = new Set();
    for (const m of mine.sort((x, y) => y.plausibility - x.plausibility)) {
      const k = m.candidates.slice(1).sort().join() + '|' + m.clues.slice().sort().join();
      if (seen.has(m.candidates.slice(1).sort().join()) || seen.size >= 4) continue;
      seen.add(m.candidates.slice(1).sort().join()); out.push(m); void k;
    }
  }
  return out;
}

// ---------- Continuum ----------
const metricRef = {population: 'SP.POP.TOTL', area: 'AG.SRF.TOTL.K2'};
const MIN_RATIO = {population: 1.15, area: 1.1};
function metricValue(id, metric) {
  const c = byId[id], r = snap.wb[id]?.[metricRef[metric]];
  if (!c || !r || defect(c, metric) || !Number.isFinite(c[metric])) return null;
  if (Math.abs(c[metric] / r.value - 1) > 0.005) return null; // game value must match the pinned reference
  return {value: c[metric], year: r.year};
}
const contPool = snap.countries.filter(c => !SENSITIVE.has(c.id) && c.population > 2e6);
function headToHead() {
  const out = [];
  for (const metric of ['population', 'area']) {
    const other = metric === 'population' ? 'area' : 'population';
    for (let i = 0; i < contPool.length; i++) for (let j = i + 1; j < contPool.length; j++) {
      const [a, b] = [contPool[i], contPool[j]];
      const va = metricValue(a.id, metric), vb = metricValue(b.id, metric);
      if (!va || !vb) continue;
      const ratio = Math.max(va.value, vb.value) / Math.min(va.value, vb.value);
      if (ratio < MIN_RATIO[metric] || ratio > 1.6) continue;
      const winner = va.value > vb.value ? a : b, loser = winner === a ? b : a;
      // Counter-intuitive: the winner is smaller on the other metric by at least 1.5×.
      const counter = byId[loser.id][other] / byId[winner.id][other];
      if (counter < 1.5 || defect(winner, other) || defect(loser, other)) continue;
      out.push({format: 'head-to-head', metric, choices: [a.id, b.id], answer: winner.id, values: {[a.id]: va, [b.id]: vb}, ratio: +ratio.toFixed(3), counterRatio: +counter.toFixed(2)});
    }
  }
  return out;
}
function missingSlot() {
  const out = [], perTarget = {};
  for (const metric of ['population', 'area']) {
    const ranked = contPool.map(c => ({id: c.id, v: metricValue(c.id, metric)})).filter(x => x.v).sort((x, y) => x.v.value - y.v.value);
    for (let t = 0; t < ranked.length; t++) for (let l = 0; l < ranked.length; l++) for (let h = l + 1; h < ranked.length; h++) {
      if (t === l || t === h) continue;
      const [T, L, H] = [ranked[t], ranked[l], ranked[h]];
      if (H.v.value / L.v.value < 1.35 || H.v.value / L.v.value > 6) continue;
      const slot = T.v.value < L.v.value ? 'below' : T.v.value > H.v.value ? 'above' : 'between';
      const nearest = Math.min(...[L, H].map(x => Math.max(x.v.value, T.v.value) / Math.min(x.v.value, T.v.value)));
      if (nearest < MIN_RATIO[metric]) continue;
      const bigOther = metric === 'population' ? 'area' : 'population';
      if ([T, L, H].some(x => defect(byId[x.id], bigOther))) continue;
      const o = x => byId[x.id][bigOther];
      const otherSlot = o(T) < Math.min(o(L), o(H)) ? 'below' : o(T) > Math.max(o(L), o(H)) ? 'above' : 'between';
      if (otherSlot === slot || o(L) > o(H) === false && slot === 'between' && otherSlot === 'between') continue;
      if ((perTarget[metric + T.id] = (perTarget[metric + T.id] ?? 0) + 1) > 4) continue;
      out.push({format: 'missing-slot', metric, target: T.id, anchors: [L.id, H.id], slot, otherMetricSlot: otherSlot, nearestRatio: +nearest.toFixed(3),
        values: Object.fromEntries([T, L, H].map(x => [x.id, x.v]))});
    }
  }
  return out;
}

// ---------- Whenabouts ----------
const LATEST = safeLatest(new Date(`${TODAY}T12:00:00Z`));
function whenEvents() {
  const seen = new Map();
  for (const p of snap.puzzles) for (const e of p.events) {
    const k = String(e.id);
    const rec = seen.get(k) ?? {event: e, dates: []};
    rec.dates.push(p.playDate); seen.set(k, rec);
  }
  const facts = new Map(snap.facts.whenabouts.map(f => [String(f.subjectId), f]));
  return [...seen.values()].map(({event: e, dates}) => ({
    id: String(e.id), title: e.title, year: e.year, month: e.month ?? null, day: e.day ?? null, tier: e.popularity_tier,
    dates: dates.sort(), ended: dates.every(d => d <= LATEST), fact: facts.get(String(e.id)) ?? null,
    titleLeaksNumber: /\b\d{3,4}\b/.test(e.title),
  }));
}
function guessYear(events) {
  return events.filter(e => e.ended && e.fact && !e.titleLeaksNumber && e.year >= -3000).map(e => {
    const gap = e.year >= 1800 ? 12 : e.year >= 1000 ? 40 : 150;
    const shift = Number(e.id) % 3; // rotate the answer's position deterministically
    const choices = [0, 1, 2].map(i => e.year + (i - shift) * gap);
    return {format: 'guess-the-year', event: e.id, title: e.title, year: e.year, choices, answerIndex: shift, tier: e.tier, fact: e.fact.id, appearances: e.dates};
  });
}
function beforeAfter(events) {
  const ok = events.filter(e => e.ended && e.fact && !e.titleLeaksNumber);
  const out = [];
  for (const x of ok) for (const y of ok) {
    if (x.id === y.id || y.tier < 4) continue; // anchor must be widely known (tier 4–5; 5 = most familiar)
    const gap = Math.abs(yearsBetween(x.year, y.year));
    const minGap = Math.min(x.year, y.year) >= 1500 ? 10 : 30;
    if (gap < minGap || gap > 120) continue;
    out.push({format: 'before-after', event: x.id, title: x.title, year: x.year, anchor: y.id, anchorTitle: y.title, anchorYear: y.year,
      answer: x.year < y.year ? 'before' : 'after', gapYears: gap, tiers: [x.tier, y.tier]});
  }
  return out;
}

// ---------- Tectonic ----------
const landNeighbors = id => {
  const g = globeById[id]; if (!g) return [];
  const fb = fbBorders(id);
  return g.neighbors.filter(n => fb.has(n) && globeById[n]);
};
function neighborClues() {
  const out = [];
  const universe = snap.globe.map(g => g.id);
  for (const t of snap.globe) {
    if (CONTESTED_MAP.has(t.id)) continue;
    const ln = landNeighbors(t.id).filter(n => !CONTESTED_MAP.has(n));
    if (landNeighbors(t.id).some(n => CONTESTED_MAP.has(n))) continue;
    for (let i = 0; i < ln.length; i++) for (let j = i + 1; j < ln.length; j++) for (let k = j + 1; k < ln.length; k++) {
      const shown = [ln[i], ln[j], ln[k]];
      const matches = universe.filter(u => shown.every(s => landNeighbors(u).includes(s)));
      if (matches.length !== 1 || matches[0] !== t.id) continue;
      // Pairwise counts show how much each clue narrows the field.
      const after1 = universe.filter(u => landNeighbors(u).includes(shown[0])).length;
      const after2 = universe.filter(u => shown.slice(0, 2).every(s => landNeighbors(u).includes(s))).length;
      out.push({format: 'neighbor-clues', answer: t.id, name: t.name, shown, allNeighbors: ln.length === 3 && landNeighbors(t.id).length === 3,
        totalLandNeighbors: landNeighbors(t.id).length, candidateCounts: [after1, after2, 1]});
    }
  }
  return out;
}
function missingCountry() {
  const out = [];
  for (const t of snap.globe) {
    const ln = landNeighbors(t.id);
    if (ln.length < 2 || CONTESTED_MAP.has(t.id)) continue;
    const ring2 = new Set(ln.flatMap(n => landNeighbors(n)));
    if ([...ln, ...ring2].some(n => CONTESTED_MAP.has(n))) continue;
    const peers = snap.globe.filter(g => g.id !== t.id && g.subregion === t.subregion && !CONTESTED_MAP.has(g.id) && !ln.includes(g.id));
    out.push({format: 'missing-country', answer: t.id, name: t.name, neighbors: ln, subregion: t.subregion, areaSr: t.areaSr,
      decoyPool: peers.map(p => p.id)});
  }
  return out;
}

const events = whenEvents();
const result = {
  snapshotId: snap.manifest.snapshotId, snapshotHash: snap.manifest.snapshotHash, generatedFor: TODAY,
  rules: {
    scalarAnswersExclude: `SENSITIVE list and Scalar Countries Daily picks ${TODAY} + ${PICK_WINDOW_DAYS} days`,
    numericMargin: MARGIN, continuumMinRatio: MIN_RATIO, whenaboutsLatestEndedDate: LATEST,
  },
  predicates: P.map(({id, text, field, kind}) => ({id, text, field, kind, usable: !refDisagreements[id]})),
  referenceDisagreements: refDisagreements,
  upcomingScalarPicks: Object.fromEntries(picks),
  scalar: {progressiveClues: scalarClues(), candidateElimination: scalarElimination()},
  continuum: {headToHead: headToHead(), missingSlot: missingSlot()},
  whenabouts: {events: events.length, endedEvents: events.filter(e => e.ended).length, guessTheYear: guessYear(events), beforeAfter: beforeAfter(events)},
  tectonic: {neighborClues: neighborClues(), missingCountry: missingCountry()},
};
const outFile = args.out ? resolve(ROOT, args.out) : resolve(snap.dir, 'candidates.json');
const text = JSON.stringify(result) + '\n';
if (!args.out && existsSync(outFile) && readFileSync(outFile, 'utf8') !== text)
  throw new Error(`${outFile} exists with different content (frozen evidence); write elsewhere with --out=`);
mkdirSync(dirname(outFile), {recursive: true});
if (!existsSync(outFile) || readFileSync(outFile, 'utf8') !== text) writeFileSync(outFile, text); // identical: leave the file untouched
const n = o => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, Array.isArray(v) ? v.length : v]));
console.log(JSON.stringify({referenceDisagreements: refDisagreements, scalar: n(result.scalar), continuum: n(result.continuum), whenabouts: n(result.whenabouts), tectonic: n(result.tectonic), latestEnded: LATEST}, null, 1));
