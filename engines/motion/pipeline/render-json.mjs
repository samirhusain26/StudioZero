// render.json for a validated motion job (tools/RENDER_JSON.md): what the packager reads instead of status.json.
// render.mjs writes it when a job validates (and for validated jobs that predate it). From the command line, for
// jobs that have none yet:
//   node engines/motion/pipeline/render-json.mjs --batch=<batchId> [--dir=<batch dir>] [--out=<jobs dir>]
// --out writes into another jobs folder (same <episodeId>/ layout), e.g. a temp copy for the packager regression;
// a finalized batch is only ever read.
import {readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {ROOT, STUDIO} from './lib.mjs';
import {motionRenderJsonCore, renderJsonText} from './render-json-core.mjs';

const KIT = resolve(STUDIO, 'src/projects/scalargame');
/** The render.json document for one validated job (input.json + status.json as written by episodes.mjs/render.mjs). */
export function motionRenderJson(input, status, beds) {
  if (status?.state !== 'validated') throw new Error(`${input.episodeId}: job not validated`);
  const bedId = input.props.music.bed.replace(/\.m4a$/, '');
  const styleSrc = readFileSync(resolve(KIT, `styles/${input.styleId}.ts`), 'utf8');
  const fonts = [...new Set([...styleSrc.matchAll(/font(?:Display|Body|Number):\s*FONT\.(\w+)/g)].map(m => m[1]))];
  return motionRenderJsonCore({input, createdAt: status.validatedAt, video: status.video, cover: status.cover, bed: beds[bedId], bedId, fonts,
    job: {codeHash: status.codeHash, coverFrame: status.coverFrame, renderer: 'render.sh'}});
}

export const loadBeds = () => JSON.parse(readFileSync(resolve(STUDIO, 'public/episodes/music/beds.json'), 'utf8'));

/** Write <jobs dir>/<id>/render.json for every validated job in `jobsDir` that has none in `outDir` (default: same). */
export function writeRenderJsons(jobsDir, outDir = jobsDir) {
  const beds = loadBeds(), written = [];
  for (const id of readdirSync(jobsDir).sort()) {
    const statusPath = resolve(jobsDir, id, 'status.json');
    if (!existsSync(statusPath)) continue;
    const status = JSON.parse(readFileSync(statusPath, 'utf8'));
    const target = resolve(outDir, id, 'render.json');
    if (status.state !== 'validated' || existsSync(target)) continue;
    const input = JSON.parse(readFileSync(resolve(jobsDir, id, 'input.json'), 'utf8'));
    mkdirSync(resolve(outDir, id), {recursive: true});
    writeFileSync(target, renderJsonText(motionRenderJson(input, status, beds)));
    written.push(id);
  }
  return written;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v = true] = a.replace(/^--/, '').split('='); return [k, v]; }));
  if (!args.batch) throw new Error('--batch=<batchId> required');
  const batchDir = resolve(ROOT, args.dir ?? `library/${args.batch}`);
  const out = args.out ? resolve(ROOT, args.out) : resolve(batchDir, 'review/jobs');
  if (!args.out && existsSync(resolve(batchDir, 'READY_FOR_UPLOAD'))) throw new Error(`${args.batch} is finalized; pass --out=<another jobs dir>`);
  console.log(JSON.stringify({batch: args.batch, written: writeRenderJsons(resolve(batchDir, 'review/jobs'), out)}));
}
