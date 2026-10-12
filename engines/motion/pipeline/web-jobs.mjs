// Studio job bundle for the in-browser export (docs/STUDIO_PLAN.md §1 decision 8): one JSON file with everything the
// browser needs to preview, export and package a batch's frozen jobs: each job's input.json (props), the checked
// questions they use, the set's CONFIG fields the packager reads, the independent source check, style recipes and
// fonts, music bed entries, and the public studio.json / project.json.
//   node engines/motion/pipeline/web-jobs.mjs --batch=<batchId> [--set=questions-<set>] [--dir=<batch dir>] [--only=a,b]
// Writes <batch dir>/review/web-jobs.json. It may name unposted answers: it stays out of git (review/ is ignored) and
// is opened in Studio › Export on the device that renders; it is never uploaded anywhere.
import {readFileSync, writeFileSync, existsSync, readdirSync} from 'node:fs';
import {resolve, relative} from 'node:path';
import {execFileSync} from 'node:child_process';
import {ROOT, STUDIO, loadSet, BATCH_ID} from './lib.mjs';
import {loadStudio} from '../../../tools/package.mjs';
import {recipeOf} from '../../../projects/scalargame/package.mjs';

export const KIND = 'studio-motion-jobs';

export async function webJobs({batch, set, dir, only, now = new Date()}) {
  if (!BATCH_ID.test(batch ?? '')) throw new Error('--batch=YYYY-MM-slug required');
  const batchDir = resolve(ROOT, dir ?? `library/${batch}`);
  if (existsSync(resolve(batchDir, 'READY_FOR_UPLOAD'))) throw new Error(`${batch} is finalized; nothing is left to export.`);
  const jobsDir = resolve(batchDir, 'review/jobs');
  if (!existsSync(jobsDir)) throw new Error(`${relative(ROOT, jobsDir)} does not exist: freeze the job inputs first (episodes.mjs).`);
  const pick = only ? new Set(String(only).split(',')) : null;
  const jobs = readdirSync(jobsDir).sort().filter(id => existsSync(resolve(jobsDir, id, 'input.json')) && (!pick || pick.has(id)))
    .map(id => JSON.parse(readFileSync(resolve(jobsDir, id, 'input.json'), 'utf8')));
  if (!jobs.length) throw new Error('no frozen job inputs to bundle');

  const SET = await loadSet(set ?? 'questions-2026-10');
  const C = SET.config;
  if (!C.batches.includes(batch)) throw new Error(`${batch} is not in ${SET.name} CONFIG.batches (${C.batches.join(', ')}); pass --set=`);
  const doc = JSON.parse(readFileSync(SET.checkedPath, 'utf8'));
  const keys = new Set(jobs.map(j => j.questionKey));
  const questions = doc.questions.filter(q => keys.has(q.key));
  if (questions.length !== keys.size) throw new Error(`${SET.name} lacks some questions the jobs use`);
  const allBeds = JSON.parse(readFileSync(resolve(STUDIO, 'public/episodes/music/beds.json'), 'utf8'));
  const beds = {};
  for (const j of jobs) {
    const id = j.props.music.bed.replace(/\.m4a$/, '');
    if (!allBeds[id]) throw new Error(`${j.episodeId}: unknown music bed ${id}`);
    beds[id] = allBeds[id];
  }
  const styles = [...new Set(jobs.map(j => j.styleId))].sort();
  const fonts = Object.fromEntries(styles.map(id => {
    const src = readFileSync(resolve(STUDIO, `src/projects/scalargame/styles/${id}.ts`), 'utf8');
    return [id, [...new Set([...src.matchAll(/font(?:Display|Body|Number):\s*FONT\.(\w+)/g)].map(m => m[1]))]];
  }));
  const verPath = resolve(ROOT, C.verification ?? resolve(batchDir, 'review/source-verification.json'));
  const verification = existsSync(verPath)
    ? {results: JSON.parse(readFileSync(verPath, 'utf8')).results.filter(r => keys.has(r.key))}
    : null;
  const {studio, projects} = loadStudio();
  const git = (...a) => execFileSync('git', ['-C', ROOT, ...a]).toString().trim();
  return {
    kind: KIND, version: 1, batchId: batch, project: 'scalargame',
    createdAt: now.toISOString().replace(/\.\d+Z$/, 'Z'), repoCommit: git('rev-parse', 'HEAD'),
    studio, projectManifest: projects.scalargame,
    set: {name: SET.name, config: {batches: C.batches, experimentId: C.experimentId, variantId: C.variantId ?? null, reviewer: C.reviewer}},
    questions: {snapshotId: doc.snapshotId, snapshotHash: doc.snapshotHash, questionsHash: doc.questionsHash, questions},
    verification, verReport: relative(ROOT, verPath),
    recipes: Object.fromEntries(styles.map(id => [id, recipeOf(id)])), fonts, beds,
    jobs,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v = true] = a.replace(/^--/, '').split('='); return [k, v]; }));
  const bundle = await webJobs(args);
  const out = resolve(ROOT, args.dir ?? `library/${args.batch}`, 'review/web-jobs.json');
  writeFileSync(out, JSON.stringify(bundle) + '\n');
  console.log(`${relative(ROOT, out)}: ${bundle.jobs.length} job(s), ${Math.round(readFileSync(out).length / 1024)} KB` +
    (bundle.verification ? '' : ' (no source check yet: export works, packaging waits for it)'));
}
