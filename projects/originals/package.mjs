// Originals' part of the shared packager (tools/package.mjs): loads review/originals.json (the reviewer's checks per
// episode) and calls the pure core (package-core.mjs): contract v2 episodes from the story engine's render.json files.
// The batch folder holds review/jobs/<episodeId>/render.json, videos/<episodeId>.mp4 and covers/<episodeId>.jpg.
import {readFileSync, existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {originalsEpisodes} from './package-core.mjs';

export async function dryRenders() {
  throw new Error('originals has no --dry mode: package a staged batch folder');
}

/** v2 batch fields from render.json documents (sorted by episodeId). Returns {generator, fields, episodes}. */
export async function packageBatch({batchDir, renders, project, studio, schemaVersion, renderHashes}) {
  if (schemaVersion !== 2) throw new Error('originals batches are contract v2');
  const path = resolve(batchDir, 'review/originals.json');
  if (!existsSync(path)) throw new Error('no review/originals.json (the reviewer\'s checks per episode)');
  const p = originalsEpisodes({renders, project, studio, review: JSON.parse(readFileSync(path, 'utf8')), renderHashes});
  for (const w of p.warnings) console.warn(`WARNING ${w}`);
  return p;
}
