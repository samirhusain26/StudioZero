// Freeze immutable per-episode render inputs for a batch.
//   node engines/motion/pipeline/episodes.mjs --batch=<batchId> [--set=questions-<set> | --set=<path/to/set.mjs>] [--dir=<batch dir>]
//   node engines/motion/pipeline/episodes.mjs --fixtures          # dev props for every question (incl. spares)
// Writes <batch dir>/review/jobs/<episodeId>/input.json (+ props.json). An existing input is never changed: if the
// content would differ the run stops (a correction needs a new revision). Episode IDs, styles and music beds come
// from the set's CONFIG (episodes, styles, beds); default set questions-2026-10 (the frozen regression set).
// A bed pool (CONFIG.beds 'calm' or a list) rotates: each new episode gets the least recently used track across the
// library (lib.mjs pickBed); an episode with a frozen input keeps its bed.
import {readFileSync, writeFileSync, mkdirSync, existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {ROOT, STUDIO, sha256, loadSnapshot, loadSet, DISPLAY_NAMES, BATCH_ID, bedPool, pickBed, libraryEpisodes} from './lib.mjs';

const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v = true] = a.replace(/^--/, '').split('='); return [k, v]; }));
const SET = await loadSet(args.set ?? 'questions-2026-10');
const {SNAPSHOT, config: CONFIG} = SET;
const doc = JSON.parse(readFileSync(SET.checkedPath, 'utf8'));
const snap = loadSnapshot(SNAPSHOT);
const timingSrc = readFileSync(resolve(STUDIO, 'src/projects/scalargame/timing.ts'), 'utf8');
const beds = JSON.parse(readFileSync(resolve(STUDIO, 'public/episodes/music/beds.json'), 'utf8'));

// Permanent IDs: <game>-<format>-<nnn>. Never reuse an ID for different content (check.mjs enforces this library-wide).
const EPISODE_IDS = CONFIG.episodes;
const STYLE = CONFIG.styles;

// Read TIMING from the TypeScript source (single source of truth) without a TS toolchain.
function timingFor(format) {
  const m = timingSrc.match(new RegExp(`'${format}':\\s*\\{([^}]*)\\}`));
  if (!m) throw new Error(`no timing for ${format}`);
  return JSON.parse(`{${m[1].replace(/(\w+):/g, '"$1":')}}`);
}

const globe = Object.fromEntries(snap.globe.map(g => [g.id, g]));
const geoCountry = id => ({id, name: globe[id].name, label: DISPLAY_NAMES[id] ?? globe[id].name, centroid: globe[id].centroid, bbox: globe[id].bbox, rings: globe[id].rings});
const inWindow = (g, w) => g.rings.some(r => r.some(([x, y]) => x >= w[0] && x <= w[2] && y >= w[1] && y <= w[3]));
/** Lon/lat bbox of a country's largest ring (by planar area): avoids antimeridian-spanning bboxes (USA, Russia, Fiji). */
function mainBbox(id) {
  const area = r => Math.abs(r.reduce((a, [x, y], i) => { const [x2, y2] = r[(i + 1) % r.length]; return a + x * y2 - x2 * y; }, 0) / 2);
  const ring = globe[id].rings.reduce((a, b) => (area(b) > area(a) ? b : a));
  const xs = ring.map(p => p[0]), ys = ring.map(p => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
function windowAround(ids, factor, minSpan) {
  const bs = ids.map(mainBbox);
  const [x0, y0, x1, y1] = [Math.min(...bs.map(b => b[0])), Math.min(...bs.map(b => b[1])), Math.max(...bs.map(b => b[2])), Math.max(...bs.map(b => b[3]))];
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, k = Math.cos(cy * Math.PI / 180);
  const span = Math.max(minSpan, factor * Math.max((x1 - x0) * k, y1 - y0));
  return [cx - span / 2 / k, cy - span / 2, cx + span / 2 / k, cy + span / 2];
}
function grow(w, factor) {
  const cx = (w[0] + w[2]) / 2, cy = (w[1] + w[3]) / 2;
  return [cx - (cx - w[0]) * factor, cy - (cy - w[1]) * factor, cx + (w[2] - cx) * factor, cy + (w[3] - cy) * factor];
}
function geoFor(q) {
  if (q.game === 'tectonic' && q.format === 'missing-country') {
    // Frame window from the checker; geometry also covers the ×2.2 pull-back after the reveal (context land only).
    const context = grow(q.geometry.frameBbox, 2.4);
    return {window: q.geometry.frameBbox, ids: snap.globe.filter(g => inWindow(g, context)).map(g => g.id)};
  }
  if (q.game === 'tectonic') {
    const core = [q.geometry.target, ...q.geometry.neighbors];
    const w = windowAround(core, 1.5, 12);
    return {window: w, ids: snap.globe.filter(g => inWindow(g, w)).map(g => g.id)};
  }
  if (q.game === 'scalar') {
    const w = windowAround([q.subjectId], 3, 30); // locator map shown after the reveal
    return {window: w, ids: snap.globe.filter(g => inWindow(g, w)).map(g => g.id)};
  }
  return {window: null, ids: []};
}

const poolFor = q => bedPool(CONFIG.beds, q, timingFor(q.format), beds);

function propsFor(q, episodeId, bed) {
  const timing = timingFor(q.format);
  const {window, ids} = geoFor(q);
  if (!STYLE[q.game]) throw new Error(`${q.key}: CONFIG.styles.${q.game} missing`);
  if (beds[bed]?.durationSeconds !== timing.duration || beds[bed]?.revealSeconds !== timing.reveal) throw new Error(`${q.key}: bed ${bed} missing from beds.json or does not match timing`);
  const durationInFrames = Math.round(timing.duration * 30);
  const {evidence, ...rest} = q;
  return {
    episodeId, styleId: STYLE[q.game], q: {...rest, evidence: {checks: evidence.checks}, geoWindow: window},
    timing, geo: ids.map(geoCountry), music: {bed: `${bed}.m4a`, volume: 0.8}, sfxVolume: 0.7, durationInFrames,
  };
}

if (args.fixtures) {
  const dir = resolve(ROOT, 'library/_dev/fixtures');
  mkdirSync(dir, {recursive: true});
  for (const q of doc.questions) writeFileSync(resolve(dir, `${q.key}.json`), JSON.stringify(propsFor(q, EPISODE_IDS[q.key]?.[1] ?? `dev-${q.key}`, poolFor(q)[0])));
  console.log(JSON.stringify({fixtures: doc.questions.length, dir}));
  process.exit(0);
}

const batch = args.batch;
if (!BATCH_ID.test(batch ?? '')) throw new Error('--batch=YYYY-MM-slug required');
const select = args.select ?? batch; // test runs: --batch=2026-10-pipelinetest --select=2026-10-pilots --dir=library/_dev/2026-10-pipelinetest
if (!CONFIG.batches.includes(select)) throw new Error(`${select} is not in ${SET.name} CONFIG.batches (${CONFIG.batches.join(', ')}); pass --set=`);
const BATCH = resolve(ROOT, args.dir ?? `library/${batch}`);
if (existsSync(resolve(BATCH, 'READY_FOR_UPLOAD'))) throw new Error(`${batch} is finalized; its inputs are immutable. Create a new batch or revision.`);
const created = [], unchanged = [];
const history = libraryEpisodes().map(e => e.bed);
for (const q of doc.questions.filter(q => EPISODE_IDS[q.key]?.[0] === select)) {
  const episodeId = EPISODE_IDS[q.key][1];
  const frozen = resolve(BATCH, 'review/jobs', episodeId, 'input.json');
  let bed;
  if (existsSync(frozen)) bed = JSON.parse(readFileSync(frozen, 'utf8')).props.music.bed.replace(/\.m4a$/, '');
  else history.push(bed = pickBed(poolFor(q), history, beds));
  const props = propsFor(q, episodeId, bed);
  const input = {
    episodeId, batchId: batch, revision: 1, questionKey: q.key, questionId: q.questionId, kitVersion: 'kit-1', styleId: props.styleId,
    snapshotId: doc.snapshotId, snapshotHash: doc.snapshotHash, questionsHash: doc.questionsHash,
    music: {bed: beds[bed]}, props, propsHash: sha256(JSON.stringify(props)),
  };
  const dir = resolve(BATCH, 'review/jobs', episodeId);
  const file = resolve(dir, 'input.json');
  if (existsSync(file) && args['replace-unrendered'] && !existsSync(resolve(dir, 'status.json'))) {
    // Never rendered: the input has not been used yet, so it may still be replaced (recorded in replacedInputs).
    const old = JSON.parse(readFileSync(file, 'utf8'));
    if (old.propsHash !== input.propsHash) input.replacedInputs = [...(old.replacedInputs ?? []), {propsHash: old.propsHash, frozenAt: old.frozenAt, reason: 'replaced before first render'}];
    else { unchanged.push(episodeId); continue; }
  } else if (existsSync(file)) {
    const old = JSON.parse(readFileSync(file, 'utf8'));
    if (old.propsHash !== input.propsHash) throw new Error(`${episodeId}: frozen input differs (old ${old.propsHash.slice(0, 12)}, new ${input.propsHash.slice(0, 12)}). Create a new revision instead.`);
    unchanged.push(episodeId); continue;
  }
  mkdirSync(dir, {recursive: true});
  writeFileSync(file, JSON.stringify({...input, frozenAt: new Date().toISOString().replace(/\.\d+Z$/, 'Z')}, null, 1) + '\n');
  writeFileSync(resolve(dir, 'props.json'), JSON.stringify(props));
  created.push(episodeId);
}
console.log(JSON.stringify({batch, created, unchanged}, null, 1));
