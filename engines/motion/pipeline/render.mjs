// Resumable per-episode render jobs for a library batch.
//   node engines/motion/pipeline/render.mjs --batch=<batchId> [--dir=<batch dir>] [--only=id1,id2] [--rerender]
// Each job (library/<batch>/review/jobs/<episodeId>/) has an immutable input.json + props.json (episodes.mjs) and a
// status.json with every attempt. A job is marked `validated` only after its MP4 and cover pass every check; only then
// are they copied to videos/<id>.mp4 and covers/<id>.jpg, and render.json (tools/RENDER_JSON.md) is written next to
// render.mp4 for the packager. Failed or partial work stays in the job folder.
// Rendering never runs once the batch has READY_FOR_UPLOAD.
import {readFileSync, writeFileSync, existsSync, readdirSync, copyFileSync, mkdirSync, statSync, openSync, readSync, closeSync} from 'node:fs';
import {resolve, relative} from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {ROOT, STUDIO} from './lib.mjs';
import {motionRenderJson, loadBeds} from './render-json.mjs';

const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v = true] = a.replace(/^--/, '').split('='); return [k, v]; }));
const batch = args.batch;
if (!/^\d{4}-\d{2}-[a-z0-9-]+$/.test(batch ?? '')) throw new Error('--batch=YYYY-MM-slug required');
const BATCH = resolve(ROOT, args.dir ?? `library/${batch}`);
if (existsSync(resolve(BATCH, 'READY_FOR_UPLOAD'))) throw new Error(`${batch} is finalized; files are immutable. Create a new revision/batch instead.`);
const R = resolve(STUDIO, 'node_modules/.bin/remotion');
const sha = p => createHash('sha256').update(readFileSync(p)).digest('hex');
const now = () => new Date().toISOString().replace(/\.\d+Z$/, 'Z');
const MAX_BYTES = 24_000_000;

// Everything that changes pixels or sound: the kit, templates, styles, fonts, beds, render script.
function walk(dir) { return readdirSync(dir, {withFileTypes: true}).flatMap(e => e.isDirectory() ? walk(resolve(dir, e.name)) : [resolve(dir, e.name)]); }
function codeHash() {
  const files = [...walk(resolve(STUDIO, 'src/projects/scalargame')), ...walk(resolve(STUDIO, 'public/episodes')), resolve(STUDIO, 'src/kit/sfx.tsx'), resolve(STUDIO, 'src/fonts.ts'), resolve(STUDIO, 'src/Root.tsx'),
    ...walk(resolve(STUDIO, 'public/sfx')), resolve(STUDIO, 'render/render.sh')].filter(p => !p.endsWith('.DS_Store')).sort();
  const h = createHash('sha256');
  for (const p of files) h.update(relative(ROOT, p)).update(sha(p));
  return h.digest('hex');
}

function faststart(path) {
  const fd = openSync(path, 'r'); const size = statSync(path).size; let off = 0; const buf = Buffer.alloc(16);
  try {
    while (off + 8 <= size) {
      readSync(fd, buf, 0, 16, off);
      let len = buf.readUInt32BE(0); const kind = buf.toString('latin1', 4, 8);
      if (len === 1) len = Number(buf.readBigUInt64BE(8)); else if (len === 0) len = size - off;
      if (kind === 'moov') return true; if (kind === 'mdat' || len < 8) return false; off += len;
    }
  } finally { closeSync(fd); }
  return false;
}

function run(cmd, argv, env = {}) {
  const r = spawnSync(cmd, argv, {cwd: STUDIO, env: {...process.env, ...env}, encoding: 'utf8', maxBuffer: 1 << 26});
  return {ok: r.status === 0, out: (r.stdout ?? '') + (r.stderr ?? '')};
}

/** Technical QA of one MP4 against the delivery spec and the job's props. Returns {measures, errors}. */
function qa(mp4, props) {
  const errors = [];
  const probe = JSON.parse(run(R, ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', mp4]).out || '{}');
  const v = probe.streams?.find(s => s.codec_type === 'video'), a = probe.streams?.find(s => s.codec_type === 'audio');
  const m = {
    bytes: statSync(mp4).size, durationSeconds: +Number(probe.format?.duration).toFixed(3), width: v?.width, height: v?.height,
    fps: v?.avg_frame_rate, videoCodec: v?.codec_name, pixFmt: v?.pix_fmt, audioCodec: a?.codec_name ?? null,
    audioSampleRate: a ? +a.sample_rate : null, audioChannels: a?.channels ?? null, fastStart: faststart(mp4),
  };
  if (m.videoCodec !== 'h264' || m.pixFmt !== 'yuv420p') errors.push(`video ${m.videoCodec}/${m.pixFmt}`);
  if (m.width !== 1080 || m.height !== 1920) errors.push(`size ${m.width}x${m.height}`);
  if (m.fps !== '30/1') errors.push(`fps ${m.fps}`);
  if (m.audioCodec !== 'aac' || m.audioSampleRate !== 48000 || m.audioChannels !== 2) errors.push(`audio ${m.audioCodec} ${m.audioSampleRate} ${m.audioChannels}ch`);
  if (Math.abs(m.durationSeconds - props.durationInFrames / 30) > 0.05) errors.push(`duration ${m.durationSeconds}s`);
  if (m.bytes > MAX_BYTES) errors.push(`size ${m.bytes} > ${MAX_BYTES}`);
  if (!m.fastStart) errors.push('not fast-start');
  // Loudness, true peak, silence gaps and black frames (house target −14 LUFS ± 2, true peak ≤ −1 dBTP).
  const q = run(resolve(STUDIO, '.venv/bin/python'), [resolve(STUDIO, 'render/qa_media.py'), mp4]);
  if (!q.ok) { errors.push(`media QA failed: ${q.out.slice(-300)}`); return {measures: m, errors}; }
  Object.assign(m, JSON.parse(q.out.trim().split('\n').at(-1)));
  if (Math.abs(m.loudnessLufs + 14) > 2) errors.push(`loudness ${m.loudnessLufs} LUFS outside −14 ± 2`);
  if (m.truePeakDbtp > -1) errors.push(`true peak ${m.truePeakDbtp} dBTP above −1`);
  if (m.blackSegments) errors.push(`${m.blackSegments} black segment(s)`);
  if (m.silenceStarts.length) errors.push(`silence at ${m.silenceStarts.join(', ')}s`);
  return {measures: m, errors};
}

const jobsDir = resolve(BATCH, 'review/jobs');
const only = args.only ? new Set(String(args.only).split(',')) : null;
const ids = readdirSync(jobsDir).filter(d => existsSync(resolve(jobsDir, d, 'input.json')) && (!only || only.has(d))).sort();
const kit = codeHash();
const beds = loadBeds();
// render.json (tools/RENDER_JSON.md) is what the packager reads; written once a job validates.
const writeRender = (dir, input, status) => writeFileSync(resolve(dir, 'render.json'), JSON.stringify(motionRenderJson(input, status, beds), null, 1) + '\n');
const summary = [];
mkdirSync(resolve(BATCH, 'videos'), {recursive: true}); mkdirSync(resolve(BATCH, 'covers'), {recursive: true});

for (const id of ids) {
  const dir = resolve(jobsDir, id);
  const input = JSON.parse(readFileSync(resolve(dir, 'input.json'), 'utf8'));
  const propsPath = resolve(dir, 'props.json');
  if (sha(propsPath) !== input.propsHash) throw new Error(`${id}: props.json no longer matches its frozen input.json`);
  const statusPath = resolve(dir, 'status.json');
  const status = existsSync(statusPath) ? JSON.parse(readFileSync(statusPath, 'utf8')) : {episodeId: id, state: 'pending', attempts: []};
  const save = () => writeFileSync(statusPath, JSON.stringify(status, null, 1) + '\n');
  if (status.state === 'validated' && !args.rerender) {
    const ok = existsSync(resolve(BATCH, `videos/${id}.mp4`)) && sha(resolve(BATCH, `videos/${id}.mp4`)) === status.video.sha256;
    if (ok && !existsSync(resolve(dir, 'render.json'))) writeRender(dir, input, status);
    summary.push({id, state: ok ? 'validated (kept)' : 'validated but delivery file changed!', staleKit: status.codeHash !== kit});
    continue;
  }
  const attempt = {startedAt: now(), codeHash: kit, propsHash: input.propsHash};
  status.attempts.push(attempt); status.state = 'rendering'; save();
  const mp4 = resolve(dir, 'render.mp4'), coverPng = resolve(dir, 'cover.png'), coverJpg = resolve(dir, 'cover.jpg');
  const log = run(resolve(STUDIO, 'render/render.sh'), ['LibraryEpisode', mp4], {LIBRARY_PROPS_FILE: propsPath});
  writeFileSync(resolve(dir, `render-${status.attempts.length}.log`), log.out);
  const t = input.props.timing;
  const coverFrame = Math.round((t.infoComplete + 0.5) * 30);
  const still = log.ok ? run(R, ['still', 'src/index.ts', 'LibraryEpisode', coverPng, `--props=${propsPath}`, `--frame=${coverFrame}`, '--log=error']) : {ok: false, out: 'skipped'};
  const jpg = still.ok ? run(R, ['ffmpeg', '-v', 'error', '-y', '-i', coverPng, '-q:v', '3', coverJpg]) : {ok: false, out: 'skipped'};
  if (!log.ok || !still.ok || !jpg.ok) {
    Object.assign(attempt, {endedAt: now(), result: 'failed', error: (log.ok ? (still.ok ? jpg.out : still.out) : log.out).slice(-2000)});
    status.state = 'failed'; save(); summary.push({id, state: 'failed'}); continue;
  }
  const check = qa(mp4, input.props);
  const coverBytes = statSync(coverJpg).size;
  if (coverBytes > 2_000_000) check.errors.push(`cover ${coverBytes} bytes`);
  Object.assign(attempt, {endedAt: now(), measures: check.measures, coverFrame, coverBytes, qaErrors: check.errors});
  if (check.errors.length) {
    attempt.result = 'qa-failed'; status.state = 'failed'; save(); summary.push({id, state: 'qa-failed', errors: check.errors}); continue;
  }
  copyFileSync(mp4, resolve(BATCH, `videos/${id}.mp4`));
  copyFileSync(coverJpg, resolve(BATCH, `covers/${id}.jpg`));
  attempt.result = 'validated';
  Object.assign(status, {state: 'validated', validatedAt: now(), codeHash: kit, coverFrame,
    video: {file: `videos/${id}.mp4`, sha256: sha(resolve(BATCH, `videos/${id}.mp4`)), ...check.measures},
    cover: {file: `covers/${id}.jpg`, sha256: sha(resolve(BATCH, `covers/${id}.jpg`)), bytes: coverBytes}});
  save();
  writeRender(dir, input, status);
  summary.push({id, state: 'validated', mb: +(check.measures.bytes / 1e6).toFixed(1), lufs: check.measures.loudnessLufs, tp: check.measures.truePeakDbtp});
}
console.log(JSON.stringify({batch, kitHash: kit.slice(0, 16), jobs: summary}, null, 1));
if (summary.some(s => s.state !== 'validated' && s.state !== 'validated (kept)')) process.exitCode = 1;
