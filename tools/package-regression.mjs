// Packager regression (docs/STUDIO_PLAN.md §4.3): re-package the finalized 2026-10 batches into a temp folder with the
// generator stamp pinned to the finalized values, validate the copy, and require a byte-identical batch.json.
//   node tools/package-regression.mjs [--keep]
// Finalized folders are only read: render.json is derived from their jobs into the temp copy, media are cloned.
import {readFileSync, mkdtempSync, mkdirSync, readdirSync, copyFileSync, rmSync, constants} from 'node:fs';
import {resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {main, ROOT} from './package.mjs';
import {writeRenderJsons} from '../engines/motion/pipeline/render-json.mjs';

const BATCHES = ['2026-10-pilots', '2026-10-b01'];
const keep = process.argv.includes('--keep');
const tmp = mkdtempSync(resolve(tmpdir(), 'package-regression-'));
let failed = 0;
for (const batch of BATCHES) {
  const src = resolve(ROOT, 'library', batch), dst = resolve(tmp, batch);
  const final = JSON.parse(readFileSync(resolve(src, 'batch.json'), 'utf8'));
  writeRenderJsons(resolve(src, 'review/jobs'), resolve(dst, 'review/jobs'));
  for (const folder of ['videos', 'covers']) {
    mkdirSync(resolve(dst, folder), {recursive: true});
    for (const f of readdirSync(resolve(src, folder))) copyFileSync(resolve(src, folder, f), resolve(dst, folder, f), constants.COPYFILE_FICLONE);
  }
  const status = await main(['--project=scalargame', `--batch=${batch}`, `--dir=${dst}`, `--schema=${final.schemaVersion}`, `--created-at=${final.createdAt}`,
    `--commit=${final.generator.repoCommit}`, `--dirty=${final.generator.dirty}`]);
  const diff = spawnSync('git', ['diff', '--no-index', '--exit-code', '--stat', resolve(src, 'batch.json'), resolve(dst, 'batch.json')], {stdio: 'inherit'});
  const ok = status === 0 && diff.status === 0;
  console.log(`${batch}: ${ok ? 'byte-identical and valid' : 'FAILED'}${status ? ` (validator exit ${status})` : ''}`);
  if (!ok) failed++;
}
if (keep) console.log(`kept ${tmp}`); else rmSync(tmp, {recursive: true, force: true});
process.exitCode = failed ? 1 : 0;
