// Stage finished story-engine renders into an Originals batch (the Originals playbook's "stage" step).
//   node tools/stage-story.mjs --batch=<batchId> [--dir=<batch dir>] [--number=<n>] [--library=<dir>] <render folder>...
// A render folder is what the story engine wrote: a recap's output/final/<title>/ or a series episode's
// <project>/episodes/episode_<n>/ (render.json + the MP4 + cover.jpg). For each one this:
//   - checks render.json (tools/RENDER_JSON.md) and refuses an unknown licence (contract v2 refuses it too);
//   - assigns the contract episode id originals-<format>-<nnn>: the next number not used anywhere in library/
//     (batch.json episodes and staged jobs, scratch batches in library/_dev included; --library= another folder, for
//     tests), or --number (1–9999) for the first;
//   - copies the MP4 and cover to review/jobs/<id>/{render.mp4, cover.jpg}, videos/<id>.mp4 and covers/<id>.jpg,
//     and a recap's script.json next to them (for the script check);
//   - writes review/jobs/<id>/render.json: the engine's document with the contract id, the staged file names and
//     job.workId = the engine's own id (media hashes unchanged, so the packager's checks still hold);
//   - adds the episode to review/originals.json with every check false (the playbook's checkpoints set them).
// Staging the same render twice is a no-op (matched on the video's sha256). Never writes into a finalized batch.
import {readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync, copyFileSync, realpathSync} from 'node:fs';
import {resolve, relative, basename, sep} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {checkRender} from './render-json-core.mjs';
import {BATCH_ID} from './package-core.mjs';

export const ROOT = resolve(import.meta.dirname, '..');
const CHECKS = ['rights', 'garbage', 'visualQa'];
const sha = p => createHash('sha256').update(readFileSync(p)).digest('hex');
const readJson = p => JSON.parse(readFileSync(p, 'utf8'));
/** A render's file, which must stay inside its folder (no absolute path, no `..`, no symlink out of it). */
function inside(folder, rel, what) {
  if (typeof rel !== 'string' || !rel || rel.startsWith('/') || rel.split(/[\\/]/).includes('..')) throw new Error(`${what}: not a relative path inside the render folder`);
  const root = realpathSync(folder), path = realpathSync(resolve(folder, rel));
  if (!path.startsWith(root + sep)) throw new Error(`${what}: points outside the render folder`);
  return path;
}
const finalized = dir => existsSync(dir) && [dir, realpathSync(dir)].some(d => existsSync(resolve(d, 'READY_FOR_UPLOAD')));

/** Every originals-<format>-<nnn> number already used under `library` (batch.json episodes and staged jobs). */
export function usedNumbers(library, format) {
  const re = new RegExp(`^originals-${format}-(\\d{3,})$`);
  const used = new Set();
  const batchDirs = [];
  for (const top of existsSync(library) ? readdirSync(library, {withFileTypes: true}) : []) {
    if (!top.isDirectory()) continue;
    if (top.name === '_dev') {
      for (const sub of readdirSync(resolve(library, top.name), {withFileTypes: true})) if (sub.isDirectory()) batchDirs.push(resolve(library, top.name, sub.name));
    } else if (!top.name.startsWith('_')) batchDirs.push(resolve(library, top.name));
  }
  for (const dir of batchDirs) {
    const ids = [];
    if (existsSync(resolve(dir, 'batch.json'))) {
      try { ids.push(...(readJson(resolve(dir, 'batch.json')).episodes ?? []).map(e => e?.episodeId)); } catch { /* not a batch */ }
    }
    if (existsSync(resolve(dir, 'review/jobs'))) ids.push(...readdirSync(resolve(dir, 'review/jobs')));
    for (const id of ids) { const m = re.exec(String(id)); if (m) used.add(Number(m[1])); }
  }
  return used;
}

function nextFree(used, from) {
  let n = from;
  while (used.has(n)) n += 1;
  return n;
}

/** Stage render folders into batchDir. Returns [{episodeId, workId, staged: true|false}]. */
export function stage({batchId, batchDir, folders, number = null, library = resolve(ROOT, 'library')}) {
  if (!BATCH_ID.test(batchId ?? '')) throw new Error('--batch=YYYY-MM-slug required');
  if (basename(batchDir) !== batchId) throw new Error(`the batch folder must be named ${batchId}`);
  if (finalized(batchDir)) throw new Error(`${batchId} is finalized; nothing may be staged into it`);
  const jobs = resolve(batchDir, 'review/jobs');
  const staged = new Map();  // video sha256 → episodeId already in this batch
  for (const id of existsSync(jobs) ? readdirSync(jobs) : []) {
    const path = resolve(jobs, id, 'render.json');
    if (existsSync(path)) staged.set(readJson(path).video?.sha256, id);
  }
  const reviewPath = resolve(batchDir, 'review/originals.json');
  const review = existsSync(reviewPath) ? readJson(reviewPath) : {reviewer: null, experimentId: null, episodes: {}};
  const out = [];
  if (number !== null && !/^[1-9]\d{0,3}$/.test(String(number))) throw new Error('--number must be a whole number from 1 to 9999');
  let next = number === null ? null : Number(number);
  for (const folder of folders) {
    const render = readJson(resolve(folder, 'render.json'));
    const errors = checkRender(render);
    if (render.engine !== 'story') errors.push('not a story-engine render');
    if (render.project !== 'originals') errors.push(`project ${render.project}, expected originals`);
    (render.credits ?? []).forEach((c, i) => { if (c?.license === 'unknown') errors.push(`credits[${i}] (${c.title}) has an unknown licence`); });
    if (!render.cover) errors.push('no cover');
    if (errors.length) throw new Error(`${relative(ROOT, resolve(folder))}/render.json: ${errors.join('; ')}`);
    const video = inside(folder, render.video.file, 'video.file'), cover = inside(folder, render.cover.file, 'cover.file');
    if (sha(video) !== render.video.sha256) throw new Error(`${render.video.file} differs from its render.json`);
    if (sha(cover) !== render.cover.sha256) throw new Error(`${render.cover.file} differs from its render.json`);
    if (staged.has(render.video.sha256)) {
      out.push({episodeId: staged.get(render.video.sha256), workId: render.episodeId, staged: false});
      continue;
    }
    const format = render.job?.format;
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(format ?? '')) throw new Error(`${render.episodeId}: job.format missing`);
    const used = usedNumbers(library, format);
    for (const id of staged.values()) { const m = /-(\d{3,})$/.exec(id); if (m && id.startsWith(`originals-${format}-`)) used.add(Number(m[1])); }
    const n = nextFree(used, next ?? 1);
    if (next !== null) next = n + 1;
    const episodeId = `originals-${format}-${String(n).padStart(3, '0')}`;
    const job = resolve(jobs, episodeId);
    mkdirSync(job, {recursive: true});
    for (const sub of ['videos', 'covers']) mkdirSync(resolve(batchDir, sub), {recursive: true});
    copyFileSync(video, resolve(job, 'render.mp4'));
    copyFileSync(cover, resolve(job, 'cover.jpg'));
    copyFileSync(video, resolve(batchDir, 'videos', `${episodeId}.mp4`));
    copyFileSync(cover, resolve(batchDir, 'covers', `${episodeId}.jpg`));
    const jobFields = {...render.job, workId: render.episodeId};
    if (render.job?.script && existsSync(resolve(folder, String(render.job.script)))) {
      copyFileSync(inside(folder, render.job.script, 'job.script'), resolve(job, 'script.json'));
      jobFields.script = 'script.json';
    }
    const doc = {...render, episodeId, job: jobFields, video: {...render.video, file: 'render.mp4'}, cover: {...render.cover, file: 'cover.jpg'}};
    writeFileSync(resolve(job, 'render.json'), JSON.stringify(doc, null, 2) + '\n');
    review.episodes[episodeId] = {checks: Object.fromEntries(CHECKS.map(k => [k, false]))};
    staged.set(render.video.sha256, episodeId);
    out.push({episodeId, workId: render.episodeId, staged: true});
  }
  mkdirSync(resolve(batchDir, 'review'), {recursive: true});
  writeFileSync(reviewPath, JSON.stringify(review, null, 2) + '\n');
  return out;
}

export function main(argv) {
  const args = Object.fromEntries(argv.filter(a => a.startsWith('--')).map(a => { const [k, v = true] = a.slice(2).split('='); return [k, v]; }));
  const folders = argv.filter(a => !a.startsWith('--'));
  if (!folders.length) throw new Error('usage: node tools/stage-story.mjs --batch=<batchId> [--dir=<batch dir>] [--number=<n>] [--library=<dir>] <render folder>...');
  const batchDir = resolve(ROOT, args.dir ?? `library/${args.batch}`);
  const result = stage({batchId: args.batch, batchDir, folders, number: args.number ?? null,
    ...(args.library ? {library: resolve(ROOT, args.library)} : {})});
  for (const r of result) console.log(JSON.stringify(r));
  return 0;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) process.exitCode = main(process.argv.slice(2));
