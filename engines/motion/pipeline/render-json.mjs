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

const KIT = resolve(STUDIO, 'src/projects/scalargame');
const FONTS = {
  fraunces: {title: 'Fraunces', creator: 'The Fraunces Project Authors', sourceUrl: 'https://github.com/undercasetype/Fraunces'},
  geist: {title: 'Geist Mono', creator: 'The Geist Project Authors', sourceUrl: 'https://github.com/vercel/geist-font'},
  montserrat: {title: 'Montserrat', creator: 'The Montserrat Project Authors', sourceUrl: 'https://github.com/JulietaUla/Montserrat'},
  plex: {title: 'IBM Plex Mono', creator: 'IBM Corp.', sourceUrl: 'https://github.com/IBM/plex'},
  nunito: {title: 'Nunito', creator: 'The Nunito Project Authors', sourceUrl: 'https://github.com/googlefonts/nunito'},
};
// Data the templates draw: maps (Scalar locator, Tectonic) and World Bank figures (Continuum).
const DATA = {
  scalar: [{kind: 'data', title: 'Natural Earth map geometry', creator: 'Natural Earth', sourceUrl: 'https://www.naturalearthdata.com/',
    license: 'public-domain', attribution: 'Made with Natural Earth', sha256: null}],
  tectonic: [{kind: 'data', title: 'Natural Earth map geometry', creator: 'Natural Earth', sourceUrl: 'https://www.naturalearthdata.com/',
    license: 'public-domain', attribution: 'Made with Natural Earth', sha256: null}],
  continuum: [{kind: 'data', title: 'World Bank population and area figures', creator: 'World Bank', sourceUrl: 'https://data.worldbank.org/',
    license: 'CC-BY-4.0', attribution: 'World Bank Open Data (CC BY 4.0)', sha256: null}],
  whenabouts: [],
};
const AI_BED = bed => bed.license === 'owner-supplied' && /AI-generated/.test(bed.rights ?? '');

/** The render.json document for one validated job (input.json + status.json as written by episodes.mjs/render.mjs). */
export function motionRenderJson(input, status, beds) {
  if (status?.state !== 'validated') throw new Error(`${input.episodeId}: job not validated`);
  const game = input.props.q.game;
  const bedId = input.props.music.bed.replace(/\.m4a$/, '');
  const bed = beds[bedId];
  if (!bed) throw new Error(`${input.episodeId}: unknown music bed ${bedId}`);
  const styleSrc = readFileSync(resolve(KIT, `styles/${input.styleId}.ts`), 'utf8');
  const fonts = [...new Set([...styleSrc.matchAll(/font(?:Display|Body|Number):\s*FONT\.(\w+)/g)].map(m => m[1]))];
  const aiBed = AI_BED(bed);
  const v = status.video;
  return {
    renderJsonVersion: 1, engine: 'motion', route: null, kitVersion: input.kitVersion, project: 'scalargame',
    episodeId: input.episodeId, createdAt: status.validatedAt,
    job: {revision: input.revision, contentKey: input.questionKey, contentId: input.questionId, styleId: input.styleId,
      musicBed: bedId, propsHash: input.propsHash, codeHash: status.codeHash, coverFrame: status.coverFrame},
    video: {file: 'render.mp4', sha256: v.sha256, bytes: v.bytes, durationSeconds: v.durationSeconds, width: v.width, height: v.height,
      fps: v.fps, videoCodec: v.videoCodec, audioCodec: v.audioCodec},
    cover: {file: 'cover.jpg', sha256: status.cover.sha256, bytes: status.cover.bytes},
    models: aiBed ? [{role: 'music', id: 'gemini (owner-supplied track)'}] : [],
    costUsd: 0, costEstimated: false,
    credits: [
      {kind: 'music', title: bed.title, creator: aiBed ? 'owner (AI-generated with Gemini)' : bed.artist ?? null, sourceUrl: bed.page ?? null,
        license: aiBed ? 'owner' : bed.license, attribution: null, sha256: bed.sha256},
      ...fonts.map(id => ({kind: 'font', ...FONTS[id], license: 'OFL-1.1', attribution: null, sha256: null})),
      {kind: 'sfx', title: 'Procedural sound effects (engines/motion/tools/make_sfx.py)', creator: 'StudioZero', sourceUrl: null, license: 'owner', attribution: null, sha256: null},
      ...DATA[game],
    ],
    disclosure: aiBed
      ? {aiGenerated: true, aiKinds: ['music'], realisticSynthetic: false, note: 'The music bed is an owner-supplied track made with Gemini; visuals, text and sound effects are not AI-generated.'}
      : {aiGenerated: false, aiKinds: [], realisticSynthetic: false, note: 'Motion graphics from templates; no AI-generated content.'},
  };
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
    writeFileSync(target, JSON.stringify(motionRenderJson(input, status, beds), null, 1) + '\n');
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
