// Shared loaders, editorial exclusions and deterministic checks for library question generation.
// Everything here reads a frozen snapshot (library/_sources/<id>/); nothing reads the live game repo.
import {existsSync, readFileSync, readdirSync} from 'node:fs';
import {resolve, basename} from 'node:path';
import {createHash} from 'node:crypto';

export const ROOT = resolve(import.meta.dirname, '../../..');   // repo root (library/, contract/)
export const STUDIO = resolve(ROOT, 'engines/motion');          // Remotion project (src/, public/, node_modules/, .venv/)
// The scalargame repo: $SCALARGAME_DIR, else the parent (repo at scalargame/marketing) or the sibling ../scalargame.
export const GAME_DIR = process.env.SCALARGAME_DIR ? resolve(process.env.SCALARGAME_DIR)
  : [resolve(ROOT, '..'), resolve(ROOT, '../scalargame')].find(d => existsSync(resolve(d, 'src/games/registry.ts')));
export const sha256 = v => createHash('sha256').update(typeof v === 'string' || ArrayBuffer.isView(v) ? v : JSON.stringify(v)).digest('hex');

// D13: avoid current tragedies/active conflicts and contested sovereignty. Conservative on purpose.
// SENSITIVE: not used as an answer, comparison subject or displayed clue in any game.
export const SENSITIVE = new Set(['AFG', 'BFA', 'COD', 'ETH', 'HTI', 'IRN', 'ISR', 'LBN', 'LBY', 'MLI', 'MMR', 'NER', 'PRK', 'PSE', 'RUS', 'SDN', 'SSD', 'SDS', 'SOM', 'SYR', 'UKR', 'YEM', 'TWN']);
// CONTESTED: sovereignty or active border disputes. Never drawn anywhere in a Tectonic frame.
export const CONTESTED = new Set(['PSE', 'ISR', 'TWN', 'CYP', 'MAR', 'ESH', 'ARM', 'AZE', 'GEO', 'MDA', 'SRB', 'XKX', 'IND', 'PAK', 'CHN', 'KOR', 'PRK', 'RUS', 'UKR', 'SDN', 'SSD', 'SDS', 'SOM', 'KGZ', 'TJK', 'UZB', 'THA', 'KHM', 'BTN', 'NPL', 'LBN', 'SYR']);
// CONTESTED_MAP: not usable as a Tectonic answer, labelled clue or choice. SENSITIVE countries may still
// appear as unlabelled context land in a frame; CONTESTED ones may not appear at all.
export const CONTESTED_MAP = new Set([...SENSITIVE, ...CONTESTED]);
// Game data defects documented in the game repo that must not become clues (HEAD area for Canada includes marine area).
export const MARGIN = 0.03; // numeric thresholds: a value within 3% counts as ambiguous (matches either side)
export const FIELD_DEFECTS = {CAN: ['area', 'pop_density']};

export function loadSnapshot(id) {
  const dir = resolve(ROOT, 'library/_sources', id);
  const read = p => readFileSync(resolve(dir, p), 'utf8');
  const json = p => JSON.parse(read(p));
  const manifest = json('manifest.json');
  const csv = p => {
    const [head, ...rows] = read(p).trim().split(/\r?\n/).map(splitCsv);
    return rows.map(r => Object.fromEntries(head.map((h, i) => [h, r[i]])));
  };
  const countries = json('src/scalar/assets/data/gameData.json').categories.countries;
  const factbook = Object.fromEntries(csv('data/reference/cia_factbook.csv').map(r => [r.iso3, r]));
  const wb = {};
  for (const r of csv('data/reference/world_bank.csv')) (wb[r.iso3] ??= {})[r.indicator] = {value: Number(r.value), year: Number(r.year)};
  const globe = json('public/tectonic/globe/countries.json').countries;
  const puzzleFiles = readdirSync(resolve(dir, 'public/puzzles')).filter(f => /^\d{4}-\d{2}\.json$/.test(f)).sort();
  const puzzles = puzzleFiles.flatMap(f => json(`public/puzzles/${f}`));
  const facts = {
    scalar: json('src/learning/facts/scalar.json').facts,
    whenabouts: json('src/learning/facts/whenabouts.json').facts,
    continuum: json('src/learning/facts/continuum.json'),
    tectonic: json('public/tectonic/facts/country_facts.json').countries,
  };
  // Retrieval dates and the Factbook mirror commit of the pinned references, as recorded in the snapshot's README.
  const refReadme = read('data/reference/README.md');
  const retrieved = file => refReadme.match(new RegExp(`\\| \`${file.replace('.', '\\.')}\` \\|[^\\n]*?\\| (\\d{4}-\\d{2}-\\d{2}) \\|`))?.[1];
  const references = {worldBankRetrieved: retrieved('world_bank.csv'), factbookRetrieved: retrieved('cia_factbook.csv'),
    factbookCommit: refReadme.match(/factbook\.json` mirror at commit `([0-9a-f]{40})`/)?.[1]};
  if (Object.values(references).some(v => !v)) throw new Error(`${id}: cannot read reference dates/commit from data/reference/README.md`);
  return {dir, manifest, countries, factbook, wb, globe, puzzles, facts, references};
}

// ---------- per-batch configuration ----------
/** Short format names used in episode IDs: <game>-<short>-<nnn>. */
export const FORMAT_SHORT = {'progressive-clues': 'clues', 'candidate-elimination': 'elimination', 'head-to-head': 'headtohead', 'missing-slot': 'slot',
  'guess-the-year': 'year', 'before-after': 'beforeafter', 'missing-country': 'missing', 'neighbor-clues': 'neighbors'};
export const DIFFICULTIES = ['approachable', 'moderate', 'challenging'];
export const BATCH_ID = /^\d{4}-\d{2}-[a-z0-9-]+$/;
/** `--set`/`--questions` → set module path: a bare name is engines/motion/pipeline/<name>.mjs; a path (with /) is relative to the repo root. */
export const setPath = arg => arg.includes('/') ? resolve(ROOT, arg.endsWith('.mjs') ? arg : `${arg}.mjs`) : resolve(import.meta.dirname, arg.endsWith('.mjs') ? arg : `${arg}.mjs`);

/**
 * Load a curated question set and its per-batch CONFIG (see engines/motion/pipeline/README.md, "Per-batch config").
 * The checked set lives at <CONFIG.outDir ?? library/_sources/<SNAPSHOT>>/<set>.json; pack.mjs reads the candidates
 * from CONFIG.candidates ?? <same folder>/candidates.json.
 */
export async function loadSet(arg) {
  const file = setPath(arg);
  const mod = await import(file);
  const name = basename(file, '.mjs');
  const C = mod.CONFIG;
  if (!C) throw new Error(`${name}: no CONFIG export (per-batch config, see engines/motion/pipeline/README.md)`);
  for (const k of ['batches', 'scope', 'styles', 'beds', 'episodes', 'experimentId', 'reviewer'])
    if (C[k] === undefined) throw new Error(`${name}: CONFIG.${k} is required`);
  for (const b of C.batches) if (!BATCH_ID.test(b)) throw new Error(`${name}: bad batch ID ${b}`);
  const outDir = resolve(ROOT, C.outDir ?? `library/_sources/${mod.SNAPSHOT}`);
  return {...mod, file, name, config: C, outDir, checkedPath: resolve(outDir, `${name}.json`), candidatesPath: resolve(ROOT, C.candidates ?? resolve(outDir, 'candidates.json'))};
}

/**
 * Every episode the library already knows: library/<batch>/batch.json episodes plus frozen job inputs
 * (library/<batch>/review/jobs/<id>/input.json) of batches not packaged yet. Folders starting with _ are scratch.
 */
export function libraryEpisodes() {
  const lib = resolve(ROOT, 'library'), out = [];
  for (const b of readdirSync(lib, {withFileTypes: true}).filter(d => d.isDirectory() && !d.name.startsWith('_')).map(d => d.name).sort()) {
    const seen = new Set();
    const bj = resolve(lib, b, 'batch.json');
    if (existsSync(bj)) for (const e of JSON.parse(readFileSync(bj, 'utf8')).episodes) {
      seen.add(e.episodeId); out.push({batchId: b, episodeId: e.episodeId, questionId: e.questionId, bed: e.music?.trackId.split(':').pop() ?? null});
    }
    const jobs = resolve(lib, b, 'review/jobs');
    if (existsSync(jobs)) for (const id of readdirSync(jobs).sort()) {
      const f = resolve(jobs, id, 'input.json');
      if (!seen.has(id) && existsSync(f)) {
        const input = JSON.parse(readFileSync(f, 'utf8'));
        out.push({batchId: b, episodeId: id, questionId: input.questionId, bed: input.props.music?.bed.replace(/\.m4a$/, '') ?? null});
      }
    }
  }
  return out;
}

/**
 * Beds a question may use. CONFIG.beds is 'calm' or a map format → bed name | [bed names] | 'calm'. 'calm' is every
 * library bed for the question's game whose duration and reveal match its timing (music_beds.py --picks). With no
 * timing (batch --dry stand-ins) only the game is matched.
 */
export function bedPool(spec, q, timing, beds) {
  const s = spec === 'calm' ? 'calm' : spec?.[q.format];
  const pool = s === 'calm'
    ? Object.values(beds).filter(b => b.game === q.game && (!timing || (b.durationSeconds === timing.duration && b.revealSeconds === timing.reveal))).map(b => b.bed).sort()
    : [s].flat().filter(Boolean);
  if (!pool.length) throw new Error(`${q.key}: no music bed for ${q.game}/${q.format} (CONFIG.beds)`);
  for (const b of pool) {
    if (!beds[b]) throw new Error(`${q.key}: bed ${b} is not in beds.json`);
    if (timing && (beds[b].durationSeconds !== timing.duration || beds[b].revealSeconds !== timing.reveal)) throw new Error(`${q.key}: bed ${b} does not match timing`);
  }
  return pool;
}

/**
 * Rotating schedule: the pool bed whose source track has been used least, then longest ago, across `history` (bed
 * names in library order, e.g. libraryEpisodes().map(e => e.bed)). Ties break on a hash of the bed name, so the order
 * is fixed but not alphabetical. Tracks, not beds, are counted: a 20 s and a 22 s cut of one track are the same music.
 */
export function pickBed(pool, history, beds) {
  const track = b => beds[b]?.trackId ?? b;
  const uses = new Map(), last = new Map();
  history.forEach((b, i) => { if (!b) return; const t = track(b); uses.set(t, (uses.get(t) ?? 0) + 1); last.set(t, i); });
  const key = b => [uses.get(track(b)) ?? 0, last.get(track(b)) ?? -1, sha256(b)];
  return [...pool].sort((a, b) => { const x = key(a), y = key(b); return x[0] - y[0] || x[1] - y[1] || (x[2] < y[2] ? -1 : 1); })[0];
}

/** Next free <game>-<short>-<nnn> per prefix after every library episode and every ID in `taken`. Never reuses a number. */
export function nextEpisodeId(prefix, taken = []) {
  const nums = [...libraryEpisodes().map(e => e.episodeId), ...taken].filter(id => id.startsWith(`${prefix}-`)).map(id => Number(id.slice(prefix.length + 1))).filter(Number.isInteger);
  return `${prefix}-${String(Math.max(0, ...nums) + 1).padStart(3, '0')}`;
}

function splitCsv(line) {
  const out = []; let cur = '', q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (q) { if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch; }
    else if (ch === '"') q = true; else if (ch === ',') { out.push(cur); cur = ''; } else cur += ch;
  }
  out.push(cur); return out;
}

// UTC−12 ended-date rule plus the publisher's four-day safety buffer.
export function safeLatest(now = new Date()) {
  const utcMinus12 = new Date(now.getTime() - 12 * 3600000).toISOString().slice(0, 10);
  return new Date(Date.parse(`${utcMinus12}T00:00:00Z`) - 4 * 86400000).toISOString().slice(0, 10);
}

/** Scalar Countries Daily answers in [from, from+days) under the snapshot's selection code. */
export async function upcomingScalarPicks(snap, from, days) {
  const sel = await import(resolve(snap.dir, 'src/utils/dailySelection.mjs'));
  const picks = new Map();
  for (let i = 0; i < days; i++) {
    const date = new Date(Date.parse(`${from}T00:00:00Z`) + i * 86400000).toISOString().slice(0, 10);
    const e = sel.getDailyEntity('countries', snap.countries, date);
    if (!picks.has(e.id)) picks.set(e.id, date);
  }
  return picks;
}

/** On-screen country names where the dataset name is awkward for a general audience. */
export const DISPLAY_NAMES = {GBR: 'United Kingdom', USA: 'United States', CZE: 'Czechia', CIV: "Côte d'Ivoire", COG: 'Republic of the Congo', SWZ: 'Eswatini', LAO: 'Laos', COD: 'DR Congo', TZA: 'Tanzania', BRN: 'Brunei', KOR: 'South Korea', PRK: 'North Korea', SDS: 'South Sudan', VNM: 'Vietnam', IRN: 'Iran', SYR: 'Syria', RUS: 'Russia', BOL: 'Bolivia', VEN: 'Venezuela', MDA: 'Moldova', MKD: 'North Macedonia', FSM: 'Micronesia', VAT: 'Vatican City', PSE: 'Palestine', CPV: 'Cape Verde', TLS: 'Timor-Leste'};

export const fmtInt = n => Math.round(n).toLocaleString('en-US');
export function fmtCompact(n, unit = '') {
  const abs = Math.abs(n);
  const [d, s] = abs >= 1e9 ? [1e9, ' billion'] : abs >= 1e6 ? [1e6, ' million'] : abs >= 1e3 ? [1e3, ',000'] : [1, ''];
  if (d === 1e3) return fmtInt(Math.round(n / 1000) * 1000) + unit;
  const v = n / d;
  return (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1).replace(/\.0$/, '') : v.toFixed(1).replace(/\.0$/, '')) + s + unit;
}
export const yearLabel = y => (y < 0 ? `${-y} BCE` : y < 1000 ? `${y} CE` : String(y));
/** Signed year difference with no year zero (1 BCE is immediately followed by 1 CE). */
export const yearsBetween = (a, b) => (b - a) - (a < 0 && b > 0 ? 1 : 0);

// ---------- Scalar predicates ----------
/** Clue predicates over the snapshot. test(c) → true | false | null (ambiguous counts as a possible match). */
export function buildScalar(snap) {
  // numeric thresholds: a value within 3% counts as ambiguous (matches either side)
  const byId = Object.fromEntries(snap.countries.map(c => [c.id, c]));
  const globeById = Object.fromEntries(snap.globe.map(c => [c.id, c]));
  const fbBorders = id => new Set((snap.factbook[id]?.border_isos ?? '').split(/\s+/).filter(Boolean));
  const monarchy = c => /Monarchy/.test(c.government_type);
  const fbMonarchy = id => /monarchy/i.test(snap.factbook[id]?.government_type ?? '');
  const defect = (c, f) => FIELD_DEFECTS[c.id]?.includes(f);

  // Each predicate: test(c) → true | false | null (ambiguous/unknown counts as a possible match),
  // ref(c) → independent reference value or undefined when the predicate is game-defined.
  const P = [];
  const add = (id, text, field, test, ref, kind) => P.push({id, text, field, test, ref, kind});
  for (const cont of ['Africa', 'Asia', 'Europe', 'Americas', 'Oceania'])
    add(`continent=${cont}`, cont === 'Americas' ? 'In the Americas' : `In ${cont}`, 'continent', c => c.continent === cont, undefined, 'broad');
  add('landlocked', 'Landlocked', 'is_landlocked', c => c.is_landlocked === true, c => snap.factbook[c.id]?.landlocked === 'true', 'broad');
  add('coastal', 'Has a coastline', 'is_landlocked', c => c.is_landlocked === false, c => snap.factbook[c.id]?.landlocked === 'false', 'broad');
  add('island', 'No land borders', 'border_countries_count', c => c.border_countries_count === 0, c => fbBorders(c.id).size === 0, 'broad');
  for (let n = 1; n <= 10; n++)
    add(`borders=${n}`, `Shares land borders with ${n} ${n === 1 ? 'country' : 'countries'}`, 'border_countries_count',
      c => c.border_countries_count === n, c => fbBorders(c.id).size === n || (c.id === 'SGP' && n === 1), 'filter');
  add('borders>=7', 'Shares land borders with 7 or more countries', 'border_countries_count', c => c.border_countries_count >= 7, c => fbBorders(c.id).size >= 7, 'filter');
  for (const [t, label] of [[1e6, '1 million'], [5e6, '5 million'], [1e7, '10 million'], [5e7, '50 million'], [1e8, '100 million'], [2e8, '200 million']]) {
    const near = c => Math.abs(c.population / t - 1) < MARGIN;
    add(`pop>${t}`, `More than ${label} people`, 'population', c => near(c) ? null : c.population > t, c => snap.wb[c.id]?.['SP.POP.TOTL']?.value > t, 'filter');
    add(`pop<${t}`, `Fewer than ${label} people`, 'population', c => near(c) ? null : c.population < t, c => snap.wb[c.id]?.['SP.POP.TOTL']?.value < t, 'filter');
  }
  for (const [t, label] of [[1e3, '1,000 km²'], [1e4, '10,000 km²'], [1e5, '100,000 km²'], [5e5, '500,000 km²'], [1e6, '1 million km²'], [2e6, '2 million km²']]) {
    const near = c => Math.abs(c.area / t - 1) < MARGIN;
    add(`area>${t}`, `Larger than ${label}`, 'area', c => defect(c, 'area') || near(c) ? null : c.area > t, c => snap.wb[c.id]?.['AG.SRF.TOTL.K2']?.value > t, 'filter');
    add(`area<${t}`, `Smaller than ${label}`, 'area', c => defect(c, 'area') || near(c) ? null : c.area < t, c => snap.wb[c.id]?.['AG.SRF.TOTL.K2']?.value < t, 'filter');
  }
  add('tz=1', 'Uses a single time zone', 'timezone_count', c => c.timezone_count === 1, undefined, 'filter');
  add('tz>1', 'Spans more than one time zone', 'timezone_count', c => c.timezone_count > 1, undefined, 'filter');
  add('monarchy', 'Has a monarch as head of state', 'government_type', monarchy, c => fbMonarchy(c.id), 'filter');
  add('south', 'Lies entirely south of the Equator', 'geometry', c => globeById[c.id] ? globeById[c.id].bbox[3] < 0 : null, undefined, 'broad');
  add('north', 'Lies entirely north of the Equator', 'geometry', c => globeById[c.id] ? globeById[c.id].bbox[1] > 0 : null, undefined, 'broad');
  for (let i = 0; i < 26; i++) {
    const L = String.fromCharCode(65 + i);
    add(`letter=${L}`, `Name starts with ${L}`, 'name', c => c.name.normalize('NFD')[0].toUpperCase() === L, undefined, 'letter');
  }
  const pById = Object.fromEntries(P.map(p => [p.id, p]));

  // Reference agreement: where game data and the pinned reference disagree (or the reference has no
  // value), that country becomes ambiguous for the predicate: it counts as a possible match on both
  // sides, and it can never be the answer that the clue identifies.
  const refDisagreements = {};
  for (const p of P) if (p.ref) {
    const raw = p.test;
    const bad = new Set(snap.countries.filter(c => raw(c) !== null && raw(c) !== p.ref(c)).map(c => c.id));
    if (bad.size) { refDisagreements[p.id] = [...bad]; p.test = c => bad.has(c.id) ? null : raw(c); }
  }
  const usable = P;
  const possible = (c, p) => p.test(c) !== false; // true or ambiguous
  const strictly = (c, p) => p.test(c) === true;

  return {P, pById: Object.fromEntries(P.map(p => [p.id, p])), refDisagreements, usable, possible, strictly, byId, globeById, fbBorders, defect};
}
