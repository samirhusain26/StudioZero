// Scalargame's part of the shared packager (tools/package.mjs): loads the inputs on the Mac and calls the pure core
// (package-core.mjs, also bundled into the Studio UI): contract v1 or v2 episodes from the motion engine's render.json
// files, the checked question set and this project's caption rules (project.json).
// experimentId, variantId, reviewer text and the fact-check file come from the set's CONFIG; default set
// questions-2026-10 (the frozen regression set). Every episode needs an independent source check result, and a
// concern/fail needs a written resolution.
// Captions, titles, alt text, polls and first comments are deterministic templates filled from episode metadata.
// The answer appears only as one item of the complete choice list (the contract's spoiler rule); answerReply is null.
import {readFileSync, existsSync} from 'node:fs';
import {resolve, relative} from 'node:path';
import {ROOT, STUDIO, loadSet, bedPool} from '../../engines/motion/pipeline/lib.mjs';
import {scalargameEpisodes} from './package-core.mjs';
import {DATA} from '../../engines/motion/pipeline/render-json-core.mjs';

export function recipeOf(id) {
  const src = readFileSync(resolve(STUDIO, `src/projects/scalargame/styles/${id}.ts`), 'utf8');
  const summary = src.match(/summary:\s*(['"`])([\s\S]*?)\1\s*,/)?.[2];
  const version = Number(src.match(/version:\s*(\d+)/)?.[1]);
  const game = src.match(/game:\s*'(\w+)'/)?.[1];
  if (!summary || !version || !game) throw new Error(`cannot read style recipe ${id}`);
  return {styleId: id, game, version, summary};
}

/** Stand-in render.json documents for every main question (--dry): checks captions against the contract early. */
export async function dryRenders({args}) {
  const SET = await loadSet(args.set ?? 'questions-2026-10');
  const doc = JSON.parse(readFileSync(SET.checkedPath, 'utf8'));
  const beds = JSON.parse(readFileSync(resolve(STUDIO, 'public/episodes/music/beds.json'), 'utf8'));
  return doc.questions.filter(q => !q.spare).map(q => ({
    episodeId: `${q.game}-dry-${String(doc.questions.indexOf(q)).padStart(3, '0')}`,
    engine: 'motion', route: null, kitVersion: 'kit-1',
    job: {revision: 1, contentKey: q.key, styleId: SET.config.styles[q.game], musicBed: bedPool(SET.config.beds, q, null, beds)[0]},
    video: {sha256: '0'.repeat(64), bytes: 1, durationSeconds: 22, width: 1080, height: 1920, fps: '30/1', videoCodec: 'h264', audioCodec: 'aac'},
    cover: {sha256: '0'.repeat(64), bytes: 1},
    models: [], costUsd: 0, credits: DATA[q.game],
    disclosure: {aiGenerated: false, aiKinds: [], realisticSynthetic: false, note: 'Dry run stand-in.'},
  }));
}

/** Batch fields from render.json documents (sorted by episodeId). Returns {generator, fields, episodes}. */
export async function packageBatch({batchId, batchDir, renders, args, project, studio, dry, schemaVersion, renderHashes}) {
  const SET = await loadSet(args.set ?? 'questions-2026-10');
  const CONFIG = SET.config;
  if (!dry && !CONFIG.batches.includes(batchId)) throw new Error(`${batchId} is not in ${SET.name} CONFIG.batches (${CONFIG.batches.join(', ')}); pass --set=`);
  const doc = JSON.parse(readFileSync(SET.checkedPath, 'utf8'));
  const beds = JSON.parse(readFileSync(resolve(STUDIO, 'public/episodes/music/beds.json'), 'utf8'));
  const verPath = resolve(ROOT, CONFIG.verification ?? resolve(batchDir, 'review/source-verification.json'));
  if (!existsSync(verPath) && !dry) throw new Error(`no independent source check: ${relative(ROOT, verPath)} (run the fact-checker first)`);
  const verification = existsSync(verPath) ? JSON.parse(readFileSync(verPath, 'utf8')) : {results: []};
  return scalargameEpisodes({renders, project, studio, config: CONFIG, setName: SET.name, doc, beds, verification,
    verReport: relative(ROOT, verPath), recipe: recipeOf, dry, schemaVersion, renderHashes});
}
