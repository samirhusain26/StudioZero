// Committed UI bundle for the Pi (no npm build on the Pi).
//   node scripts/build-static.mjs           vite build to a temp dir, copy it to publisher/app/static/, write MANIFEST.json
//   node scripts/build-static.mjs --check   rebuild to a temp dir; fail if the committed bundle or manifest is stale
// MANIFEST.json = {files: {<path>: sha256}, sourceHash}. sourceHash covers every git-visible publisher/ui source file
// (tracked plus untracked-not-ignored; node_modules, dist and test-results excluded): sha256 over the sorted
// "<path>\0<sha256 of contents>\n" lines.
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {cpSync, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, relative, resolve, sep} from 'node:path';

const UI = resolve(import.meta.dirname, '..');
const STATIC = resolve(UI, '../app/static');
const MANIFEST = 'MANIFEST.json';
// Only what the production bundle is built from: tests, e2e and lint config never change the output.
const INPUT_DIRS = ['src/', 'public/', 'content/'];
const INPUT_FILES = ['index.html', 'package.json', 'package-lock.json', 'vite.config.ts', 'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json'];
const TEST_FILE = /(\.test\.[cm]?[jt]sx?|\/test-setup\.[jt]s|\/setupTests\.[jt]s)$/;
const isInput = p => INPUT_FILES.includes(p) || (INPUT_DIRS.some(d => p.startsWith(d)) && !TEST_FILE.test(p) && !p.startsWith('src/test/'));
const check = process.argv.includes('--check');

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const walk = dir => readdirSync(dir, {withFileTypes: true})
  .flatMap(e => e.isDirectory() ? walk(join(dir, e.name)) : [join(dir, e.name)]);
const posix = p => p.split(sep).join('/');

function fileHashes(dir) {
  const files = {};
  for (const path of walk(dir).map(p => posix(relative(dir, p))).sort()) {
    if (path !== MANIFEST && path.split('/').at(-1) !== '.DS_Store') files[path] = sha(readFileSync(join(dir, path)));
  }
  return files;
}

function sourceHash() {
  const listed = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', '.'], {cwd: UI})
    .toString().split('\0').filter(Boolean);
  const paths = [...new Set(listed)].filter(p => isInput(p) && existsSync(join(UI, p)) && statSync(join(UI, p)).isFile()).sort();
  const h = createHash('sha256');
  for (const p of paths) h.update(`${p}\0${sha(readFileSync(join(UI, p)))}\n`);
  return h.digest('hex');
}

function build() {
  const out = mkdtempSync(join(tmpdir(), 'scalar-ui-static-'));
  execFileSync(resolve(UI, 'node_modules/.bin/vite'), ['build', '--outDir', out, '--emptyOutDir', '--logLevel', 'warn'], {cwd: UI, stdio: 'inherit'});
  return out;
}

const out = build();
try {
  const manifest = {files: fileHashes(out), sourceHash: sourceHash()};
  if (!check) {
    rmSync(STATIC, {recursive: true, force: true});
    cpSync(out, STATIC, {recursive: true});
    writeFileSync(join(STATIC, MANIFEST), JSON.stringify(manifest, null, 2) + '\n');
    console.log(`publisher/app/static: ${Object.keys(manifest.files).length} files, sourceHash ${manifest.sourceHash.slice(0, 12)}`);
  } else {
    const problems = [];
    const committedPath = join(STATIC, MANIFEST);
    const committed = existsSync(committedPath) ? JSON.parse(readFileSync(committedPath, 'utf8')) : null;
    if (!committed) problems.push(`missing ${posix(relative(UI, committedPath))}`);
    else {
      if (committed.sourceHash !== manifest.sourceHash) problems.push(`sourceHash ${committed.sourceHash} != fresh ${manifest.sourceHash}`);
      const onDisk = fileHashes(STATIC);
      for (const [label, files] of [['fresh build', manifest.files], ['publisher/app/static', onDisk]]) {
        for (const path of new Set([...Object.keys(committed.files ?? {}), ...Object.keys(files)])) {
          if (committed.files?.[path] !== files[path]) problems.push(`${path}: manifest ${committed.files?.[path] ?? 'absent'} != ${label} ${files[path] ?? 'absent'}`);
        }
      }
    }
    if (problems.length) {
      console.error(`Committed UI bundle is stale (run npm run build:static):\n  ${problems.join('\n  ')}`);
      process.exitCode = 1;
    } else console.log(`publisher/app/static matches a fresh build (${Object.keys(manifest.files).length} files, sourceHash ${manifest.sourceHash.slice(0, 12)})`);
  }
} finally {
  rmSync(out, {recursive: true, force: true});
}
