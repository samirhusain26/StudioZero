// Build the static review sheet for a batch: key frames, contact sheets, phone-size player, metadata, QA, validator.
//   node engines/motion/pipeline/review.mjs --batch=<batchId> [--dir=<batch dir>] [--no-frames]
// Writes library/<batch>/review/index.html (+ frames/<episodeId>/*.png, contact/<episodeId>.png, validator.json).
import {readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {ROOT, STUDIO} from './lib.mjs';

const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v = true] = a.replace(/^--/, '').split('='); return [k, v]; }));
const batch = args.batch;
const BATCH = resolve(ROOT, args.dir ?? `library/${batch}`), REVIEW = resolve(BATCH, 'review');
if (existsSync(resolve(BATCH, 'READY_FOR_UPLOAD'))) throw new Error(`${batch} is finalized; its review folder is immutable.`);
const R = resolve(STUDIO, 'node_modules/.bin/remotion');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const run = (cmd, argv, cwd = ROOT) => spawnSync(cmd, argv, {cwd, encoding: 'utf8', maxBuffer: 1 << 26});

const data = existsSync(resolve(BATCH, 'batch.json')) ? JSON.parse(readFileSync(resolve(BATCH, 'batch.json'), 'utf8')) : null;
const v = run('python3', ['contract/library_contract.py', 'validate', BATCH, '--json']);
let validator;
try { validator = JSON.parse(v.stdout); } catch { validator = {ok: false, errors: [{path: '-', message: (v.stdout + v.stderr).slice(0, 2000)}], warnings: []}; }
writeFileSync(resolve(REVIEW, 'validator.json'), JSON.stringify(validator, null, 2) + '\n');

const ids = readdirSync(resolve(REVIEW, 'jobs')).filter(d => existsSync(resolve(REVIEW, 'jobs', d, 'input.json'))).sort();
const cards = [];
for (const id of ids) {
  const dir = resolve(REVIEW, 'jobs', id);
  const input = JSON.parse(readFileSync(resolve(dir, 'input.json'), 'utf8'));
  const status = existsSync(resolve(dir, 'status.json')) ? JSON.parse(readFileSync(resolve(dir, 'status.json'), 'utf8')) : {state: 'pending', attempts: []};
  const t = input.props.timing;
  const marks = [['hook', 0.4], ...t.items.map((s, i) => [`item ${i + 1}`, s + 0.6]), ['cover · think', t.infoComplete + 0.5], ['think end', t.reveal - 0.3],
    ['reveal', t.reveal + 1.5], ['explain', t.explain + 1], ['cta', t.cta + 1]];
  const frameDir = resolve(REVIEW, 'frames', id); mkdirSync(frameDir, {recursive: true});
  const frames = marks.map(([label, sec], i) => ({label, sec, file: `frames/${id}/${String(i).padStart(2, '0')}-${label.replace(/\W+/g, '-')}.png`}));
  if (!args['no-frames']) for (const fr of frames) {
    const r = run(R, ['still', 'src/index.ts', 'LibraryEpisode', resolve(REVIEW, fr.file), `--props=${resolve(dir, 'props.json')}`, `--frame=${Math.round(fr.sec * 30)}`, '--scale=0.5', '--log=error'], STUDIO);
    if (r.status) throw new Error(`${id}: still ${fr.label} failed\n${r.stderr}`);
  }
  const raw = data?.episodes.find(e => e.episodeId === id);
  // Contract v2 keeps the Scalargame fields under projectData and the credits on the episode itself.
  const ep = raw?.projectData ? {...raw, ...raw.projectData, publication: {credits: raw.credits.map(c => `${c.title} (${c.license})`), ...raw.publication}} : raw;
  const att = status.attempts?.at(-1) ?? {};
  const m = status.video ?? att.measures ?? {};
  const errs = (validator.errors ?? []).filter(e => data && e.path.startsWith(`episodes[${data.episodes.indexOf(raw)}]`));
  cards.push(`<section id="${id}">
<h2>${esc(id)} <small>${esc(input.questionKey)} · ${esc(ep?.difficulty ?? '')} · ${esc(input.styleId)} · state <b class="${status.state}">${esc(status.state)}</b></small></h2>
<div class="row">
  <div class="phone">${status.state === 'validated' ? `<video controls playsinline preload="metadata" poster="../covers/${id}.jpg" src="../videos/${id}.mp4"></video>` : '<div class="missing">no validated video</div>'}
  <div class="small">Phone size (360 px wide). Watch once with sound, once muted.</div></div>
  <div class="cover">${status.state === 'validated' ? `<img src="../covers/${id}.jpg" alt="cover">` : ''}<div class="small">Cover (frame ${esc(status.coverFrame)}) · ${esc(status.cover?.bytes)} bytes</div></div>
  <div class="meta">
    <table>
      <tr><th>Question</th><td>${esc(ep?.creative.hook)}<br><b>${esc(ep?.creative.question)}</b>${ep?.creative.clues?.length ? `<br>${ep.creative.clues.map(esc).join(' · ')}` : ''}</td></tr>
      <tr><th>Choices</th><td>${(ep?.creative.choices ?? []).map(c => `${c.key}) ${esc(c.label)}`).join('<br>')}</td></tr>
      <tr><th>Answer</th><td><b>${esc(ep?.creative.answer)}</b> — ${esc(ep?.creative.explanation)}</td></tr>
      <tr><th>Media</th><td>${esc(m.durationSeconds)} s · ${esc(m.width)}×${esc(m.height)} · ${esc(m.fps)} · ${esc(m.videoCodec)}/${esc(m.pixFmt)} · ${esc(m.audioCodec)} ${esc(m.audioSampleRate)} Hz ${esc(m.audioChannels)}ch · ${(m.bytes / 1e6).toFixed(2)} MB · fast-start ${esc(m.fastStart)} · ${esc(m.loudnessLufs)} LUFS · TP ${esc(m.truePeakDbtp)} dBTP · black ${esc(m.blackSegments)} · silences ${esc((m.silenceStarts ?? []).length)}</td></tr>
      <tr><th>Music</th><td>${esc(ep?.music.trackId)} (${esc(ep?.music.license)})</td></tr>
      <tr><th>Timing</th><td>info complete ${t.infoComplete}s · think ${(t.reveal - t.infoComplete).toFixed(1)}s · reveal ${t.reveal}s · explain ${t.explain}s · CTA ${t.cta}s · end ${t.duration}s</td></tr>
      <tr><th>Validator</th><td>${errs.length ? errs.map(e => `<div class="err">${esc(e.path)}: ${esc(e.message)}</div>`).join('') : '<span class="ok">no episode errors</span>'}</td></tr>
    </table>
  </div>
</div>
<div class="frames">${frames.map(fr => `<figure><img loading="lazy" src="${fr.file}"><figcaption>${esc(fr.label)} · ${fr.sec.toFixed(1)}s</figcaption></figure>`).join('')}</div>
${ep ? `<details><summary>Publication metadata</summary><table>
  ${Object.entries(ep.publication.captions).map(([p, c]) => `<tr><th>${p}</th><td><pre>${esc(c)}</pre></td></tr>`).join('')}
  <tr><th>YouTube</th><td><b>${esc(ep.publication.youtube.title)}</b><pre>${esc(ep.publication.youtube.description)}</pre></td></tr>
  <tr><th>Alt text</th><td>${esc(ep.publication.altText)}</td></tr>
  <tr><th>Poll</th><td>${esc(ep.publication.poll?.question)} — ${(ep.publication.poll?.options ?? []).map(esc).join(' / ')}</td></tr>
  <tr><th>First comment</th><td><pre>${esc(JSON.stringify(ep.publication.firstComment, null, 1))}</pre></td></tr>
  <tr><th>Hashtags / credits</th><td>${esc(ep.publication.hashtags.join(' '))} · ${esc(ep.publication.credits.join(', ') || 'none')}</td></tr>
  <tr><th>Eligibility</th><td>${esc(JSON.stringify(ep.eligibility))}</td></tr>
  <tr><th>Sources</th><td>${ep.evidence.sources.map(s => `<a href="${esc(s.url)}">${esc(s.title)}</a>`).join('<br>')}</td></tr>
</table></details>` : ''}
</section>`);
}

const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review ${esc(batch)}</title><style>
:root{--bg:#FAFAF9;--fg:#18181B;--mut:#52525B;--line:#E2E8F0;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#111113;--fg:#F4F4F5;--mut:#A1A1AA;--line:#27272A;--card:#18181B}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif;margin:0;padding:16px}
h1{margin:.2em 0}h2{font-size:18px;border-top:2px solid var(--fg);padding-top:10px;margin-top:28px}h2 small{font-weight:400;color:var(--mut)}
.row{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}.phone video{width:360px;height:640px;background:#000;display:block}
.cover img{width:180px;display:block;border:1px solid var(--line)}.meta{flex:1;min-width:320px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}th{width:110px}
.frames{display:flex;gap:8px;overflow-x:auto;margin-top:10px}.frames figure{margin:0}.frames img{height:400px;display:block;border:1px solid var(--line)}
figcaption,.small{font-size:12px;color:var(--mut)}pre{white-space:pre-wrap;margin:0;font:12px ui-monospace,monospace}
.validated,.ok{color:#15803D}.failed,.err{color:#B91C1C}.missing{width:360px;height:640px;display:grid;place-items:center;border:1px dashed var(--line)}
</style></head><body>
<h1>Review · ${esc(batch)}</h1>
<p>${ids.length} episode(s). Validator (<code>python3 contract/library_contract.py validate library/${esc(batch)}</code>): <b class="${validator.ok ? 'ok' : 'err'}">${validator.ok ? 'PASS' : 'FAIL'}</b>, ${validator.errors?.length ?? 0} error(s), ${validator.warnings?.length ?? 0} warning(s).
${(validator.warnings ?? []).map(w => `<br><span class="small">warning ${esc(w.path)}: ${esc(w.message)}</span>`).join('')}
${(validator.errors ?? []).filter(e => !/^episodes\[/.test(e.path)).map(e => `<br><span class="err">${esc(e.path)}: ${esc(e.message)}</span>`).join('')}</p>
<p class="small">Checklist: question understandable on first view · nothing reveals the answer before the reveal (cover, title, captions) · ≥ 6 s to think with everything on screen · text legible at phone size and inside the safe area · reveal is the strongest moment · explanation readable · muted playback complete · audio comfortable and in sync · closing card “Play a new puzzle · scalargame.com”.</p>
${cards.join('\n')}
</body></html>`;
writeFileSync(resolve(REVIEW, 'index.html'), html);
console.log(resolve(REVIEW, 'index.html'));
