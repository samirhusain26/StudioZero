// Freeze the canonical game sources for a library batch.
//   node studio/pipeline/snapshot.mjs [--game=<scalargame dir>] [--ref=HEAD]   (default: lib.mjs GAME_DIR)
// Reads committed files with `git show <ref>:<path>` so uncommitted game-repo edits never leak in,
// writes them under library/_sources/<snapshotId>/ with a manifest, and prints the snapshot hash.
// Re-running against the same commit reproduces the same bytes and hash.
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {mkdirSync, writeFileSync, existsSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {ROOT, GAME_DIR} from './lib.mjs';

const args = Object.fromEntries(process.argv.slice(2).map(a => a.replace(/^--/, '').split('=')));
const GAME = args.game ? resolve(ROOT, args.game) : GAME_DIR;
if (!GAME) throw new Error('scalargame repo not found: set SCALARGAME_DIR or pass --game=<dir>');
const REF = args.ref ?? 'HEAD';

const FILES = [
  'src/games/registry.ts',
  'src/utils/dailySelection.mjs',
  'src/scalar/assets/data/gameData.json',
  'src/scalar/assets/data/continuumGameData.json',
  'src/continuum/continuumConfig.ts',
  'data/reference/README.md',
  'data/reference/world_bank.csv',
  'data/reference/cia_factbook.csv',
  'data/reference/allowlist.json',
  'public/tectonic/globe/countries.json',
  'public/tectonic/globe/catalog.json',
  'public/tectonic/facts/country_facts.json',
  'src/learning/facts/scalar.json',
  'src/learning/facts/continuum.json',
  'src/learning/facts/whenabouts.json',
  'src/learning/facts/scalar-fingerprints.json',
  'src/learning/continuumFingerprints.ts',
];

const git = (...a) => execFileSync('git', ['-C', GAME, ...a], {maxBuffer: 1 << 28});
const sha256 = b => createHash('sha256').update(b).digest('hex');
const commit = git('rev-parse', REF).toString().trim();
const puzzles = git('ls-tree', '--name-only', `${REF}:public/puzzles`).toString().trim().split('\n')
  .filter(n => /^\d{4}-\d{2}\.json$/.test(n) || n === 'dates.json' || n === 'manifest.json').map(n => `public/puzzles/${n}`);
const paths = [...FILES, ...puzzles].sort();

const dirtyPaths = git('status', '--porcelain', '--', ...paths).toString().trimEnd().split('\n').filter(Boolean).map(l => l.slice(3));
const snapshotId = `${new Date().toISOString().slice(0, 10)}-${commit.slice(0, 7)}`;
const out = resolve(ROOT, 'library/_sources', args.id ?? snapshotId);
// An existing snapshot is frozen evidence: re-running would rewrite its manifest (frozenAt). Pick a new ID.
if (existsSync(resolve(out, 'manifest.json'))) throw new Error(`${out} already exists; snapshots are frozen. Reuse it or freeze a new ID.`);
const files = paths.map(path => {
  const bytes = git('show', `${REF}:${path}`);
  const target = resolve(out, path);
  mkdirSync(dirname(target), {recursive: true});
  if (!existsSync(target) || sha256(readFileSync(target)) !== sha256(bytes)) writeFileSync(target, bytes);
  return {path, sha256: sha256(bytes), bytes: bytes.length};
});
// The hash covers the commit and every file hash, not the retrieval time.
const snapshotHash = sha256(JSON.stringify({repo: 'scalargame', commit, files}));
const manifest = {
  snapshotId: args.id ?? snapshotId, snapshotHash, repo: 'scalargame', ref: REF, commit,
  frozenAt: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
  uncommittedGameEditsExcluded: dirtyPaths,
  note: 'Committed game sources only. Uncommitted working-tree edits in the game repo are excluded by construction.',
  files,
};
writeFileSync(resolve(out, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({snapshotId: manifest.snapshotId, snapshotHash, commit, files: files.length, excludedDirty: dirtyPaths}, null, 2));
