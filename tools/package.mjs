// Shared packager: render.json (every engine) + the project's captions and metadata → batch.json, then the validator.
//   node tools/package.mjs --project=<id> --batch=<batchId> [--dir=<batch dir>] [--created-at=<…Z>] [--commit=<sha>]
//                          [--dirty=true|false] [--schema=1|2] [--no-validate] [--dry] [project options, e.g. --set=questions-<set>]
// Reads <batch dir>/review/jobs/<episodeId>/render.json (tools/RENDER_JSON.md), checks the delivered videos/ and covers/
// against their hashes, writes <batch dir>/batch.json and runs contract/library_contract.py validate on the folder.
// --created-at/--commit/--dirty pin the generator stamp (the packager regression, tools/package-regression.mjs).
// --schema overrides project.json's contract version (the regression re-packages the finalized v1 batches as v1).
// v2 stamps each episode's render.renderSha256 with the sha256 of its render.json file.
// --dry: stand-in renders for every main question, no media → library/_dev/batch-dry.json (caption checks only).
// Never writes into a finalized batch (READY_FOR_UPLOAD). Engines never write batch.json.
import {readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync, realpathSync} from 'node:fs';
import {resolve} from 'node:path';
import {execFileSync, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {BATCH_ID, batchDocument, checkProject, renderErrors} from './package-core.mjs';

export const ROOT = resolve(import.meta.dirname, '..');
const sha = p => createHash('sha256').update(readFileSync(p)).digest('hex');

/** True when the batch folder (or the folder a link points to) is finalized. */
const finalized = path => existsSync(path) && [path, realpathSync(path)].some(dir => existsSync(resolve(dir, 'READY_FOR_UPLOAD')));

export function loadStudio() {
  const studio = JSON.parse(readFileSync(resolve(ROOT, 'studio.json'), 'utf8'));
  const projects = Object.fromEntries(studio.projects.map(p => [p.id, JSON.parse(readFileSync(resolve(ROOT, p.manifest), 'utf8'))]));
  return {studio, projects};
}

export async function main(argv) {
  const args = Object.fromEntries(argv.map(a => { const [k, v = true] = a.replace(/^--/, '').split('='); return [k, v]; }));
  const {studio, projects} = loadStudio();
  const project = projects[args.project];
  if (!project) throw new Error(`--project must be one of ${Object.keys(projects).join(', ')}`);
  const schemaVersion = args.schema === undefined ? project.contract.schemaVersion : Number(args.schema);
  checkProject(project, schemaVersion);
  const batchId = args.batch;
  if (!BATCH_ID.test(batchId ?? '')) throw new Error('--batch=YYYY-MM-slug required');
  const dry = Boolean(args.dry);
  const batchDir = resolve(ROOT, args.dir ?? `library/${batchId}`);
  if (!dry && finalized(batchDir)) throw new Error(`${batchId} is finalized; batch.json is immutable.`);
  const mod = await import(pathToFileURL(resolve(ROOT, project.packager)).href);

  let renders;
  const renderHashes = {};
  if (dry) renders = await mod.dryRenders({args, project, studio});
  else {
    const jobs = resolve(batchDir, 'review/jobs');
    const known = new Set(Object.keys(projects));
    renders = readdirSync(jobs).sort().map(id => {
      const path = resolve(jobs, id, 'render.json');
      if (!existsSync(path)) throw new Error(`${id}: no render.json (render and validate the job first)`);
      const render = JSON.parse(readFileSync(path, 'utf8'));
      const errors = renderErrors(render, {folder: id, project, known, schemaVersion});
      if (errors.length) throw new Error(`${id}/render.json: ${errors.join('; ')}`);
      renderHashes[id] = sha(path);
      return render;
    });
  }
  const p = await mod.packageBatch({batchId, batchDir, renders, args, project, studio, dry, schemaVersion, renderHashes});
  if (!dry) for (const ep of p.episodes) for (const kind of ['video', 'cover']) {
    const file = resolve(batchDir, ep[kind].file);
    if (!existsSync(file)) throw new Error(`${ep.episodeId}: ${ep[kind].file} missing (render.mjs copies it on validation)`);
    if (sha(file) !== ep[kind].sha256) throw new Error(`${ep.episodeId}: ${ep[kind].file} differs from its render.json`);
  }

  const git = (...a) => execFileSync('git', ['-C', ROOT, ...a]).toString().trim();
  const commit = args.commit ?? git('rev-parse', 'HEAD');
  const dirty = args.dirty === undefined ? git('status', '--porcelain').length > 0 : args.dirty === 'true';
  const createdAt = args['created-at'] ?? new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  const body = batchDocument({project, batchId, createdAt, commit, dirty, packaged: p, schemaVersion});
  if (dry) {
    mkdirSync(resolve(ROOT, 'library/_dev'), {recursive: true});
    writeFileSync(resolve(ROOT, 'library/_dev/batch-dry.json'), body);
    console.log('dry metadata: library/_dev/batch-dry.json');
  } else writeFileSync(resolve(batchDir, 'batch.json'), body);
  console.log(JSON.stringify({batch: batchId, project: project.id, schemaVersion, episodes: p.episodes.length, dirty, commit: commit.slice(0, 7)}));
  if (dry || args['no-validate']) return 0;
  const r = spawnSync('python3', [resolve(ROOT, 'contract/library_contract.py'), 'validate', batchDir], {stdio: 'inherit'});
  return r.status ?? 1;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) process.exitCode = await main(process.argv.slice(2));
