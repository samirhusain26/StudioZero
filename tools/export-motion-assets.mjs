// Motion asset manifest for the Pi (docs/STUDIO_PLAN.md §1 decision 8): the files under engines/motion/public that the
// Scalargame kit loads in the browser (fonts, live music beds, SFX), each with its sha256 and size. Committed as
// publisher/motion-assets.json; the Pi serves exactly these paths (the allowlist) from its checkout at
// /api/assets/motion/<version>/<path>, where <version> is derived from this file (the cache key).
//   node tools/export-motion-assets.mjs           write publisher/motion-assets.json
//   node tools/export-motion-assets.mjs --check   fail when it is stale (run by `npm run check:static`)
// Tracked files only (git ls-files), so the owner's local-only beds never appear; retired beds are left out too.
import {readFileSync, writeFileSync, existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {ROOT} from './package.mjs';

const OUT = resolve(ROOT, 'publisher/motion-assets.json');
const PUBLIC = 'engines/motion/public';
const KINDS = [/^episodes\/fonts\/[a-z0-9-]+\.woff2$/, /^episodes\/music\/[a-z0-9-]+\.m4a$/, /^sfx\/[a-z0-9]+\.wav$/];

export function manifest() {
  const catalog = JSON.parse(readFileSync(resolve(ROOT, 'publisher/catalog.json'), 'utf8'));
  const retired = new Set(catalog.engines.flatMap(e => e.beds ?? []).filter(b => b.retired).map(b => `episodes/music/${b.id}.m4a`));
  const tracked = execFileSync('git', ['-C', ROOT, 'ls-files', '-z', '--', PUBLIC]).toString().split('\0').filter(Boolean);
  const files = {};
  for (const path of tracked.map(p => p.slice(PUBLIC.length + 1)).sort()) {
    if (!KINDS.some(k => k.test(path)) || retired.has(path)) continue;
    const bytes = readFileSync(resolve(ROOT, PUBLIC, path));
    files[path] = {sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length};
  }
  return {motionAssetsVersion: 1, root: PUBLIC, files};
}

const body = JSON.stringify(manifest(), null, 1) + '\n';
if (process.argv.includes('--check')) {
  if (!existsSync(OUT) || readFileSync(OUT, 'utf8') !== body) {
    console.error('publisher/motion-assets.json is stale: run node tools/export-motion-assets.mjs');
    process.exit(1);
  }
  console.log('publisher/motion-assets.json matches engines/motion/public.');
} else {
  writeFileSync(OUT, body);
  console.log(`publisher/motion-assets.json: ${Object.keys(JSON.parse(body).files).length} files, ${body.length} bytes`);
}
