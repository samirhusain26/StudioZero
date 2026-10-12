// Check render.json files (engine → packager, tools/RENDER_JSON.md). Used by tools/package.mjs and the engines' tests.
//   node tools/render-json.mjs <render.json>...      exit 1 and one line per error when any file is invalid
// The check itself is render-json-core.mjs (pure, also bundled into the Studio UI).
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {checkRender} from './render-json-core.mjs';

export * from './render-json-core.mjs';

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const files = process.argv.slice(2);
  if (!files.length) { console.error('usage: node tools/render-json.mjs <render.json>...'); process.exit(2); }
  let bad = 0;
  for (const f of files) {
    let errors;
    try { errors = checkRender(JSON.parse(readFileSync(f, 'utf8'))); } catch (err) { errors = [String(err.message ?? err)]; }
    for (const m of errors) console.log(`${f}: ${m}`);
    if (errors.length) bad++;
  }
  console.log(`${files.length} render.json file(s) checked, ${bad} invalid.`);
  process.exit(bad ? 1 : 0);
}
