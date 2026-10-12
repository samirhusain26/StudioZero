// Studio catalog for the Pi (docs/STUDIO_PLAN.md §6): what each project can make, on which engine, with which
// templates, styles, beds, routes and models. Generated from studio.json, projects/*/project.json, the motion
// engine's template/style/timing/bed registries and the story engine's registry.json; committed as
// publisher/catalog.json (the Pi's sparse checkout has publisher/, so it serves the file at /api/catalog).
//   node tools/export-catalog.mjs           write publisher/catalog.json
//   node tools/export-catalog.mjs --check   fail when publisher/catalog.json is stale (run by `npm run check:static`)
// Deterministic: no timestamps; regenerate after changing any source above.
import {readFileSync, writeFileSync, existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {loadStudio, ROOT} from './package.mjs';

const OUT = resolve(ROOT, 'publisher/catalog.json');
const read = p => readFileSync(resolve(ROOT, p), 'utf8');
const json = p => JSON.parse(read(p));

function motion(engine) {
  const r = engine.registries;
  const templates = [...read(r.templates).matchAll(/^\s*'([a-z-]+)':\s*(\w+),$/gm)].map(m => ({format: m[1], component: m[2]}));
  const timing = read(r.timing);
  const timingOf = format => {
    const m = timing.match(new RegExp(`'${format}':\\s*\\{([^}]*)\\}`));
    if (!m) throw new Error(`no timing for ${format}`);
    const t = JSON.parse(`{${m[1].replace(/(\w+):/g, '"$1":')}}`);
    return {durationSeconds: t.duration, revealSeconds: t.reveal};
  };
  const styleIds = [...read(`${r.styles}/index.ts`).matchAll(/import \{style as \w+\} from '\.\/([a-z0-9-]+)'/g)].map(m => m[1]);
  const styles = styleIds.map(id => {
    const src = read(`${r.styles}/${id}.ts`);
    const summary = src.match(/summary:\s*(['"`])([\s\S]*?)\1\s*,/)?.[2]?.replace(/'\s*\+\s*'/g, '');
    const version = Number(src.match(/version:\s*(\d+)/)?.[1]);
    const game = src.match(/game:\s*'(\w+)'/)?.[1];
    if (!summary || !version || !game) throw new Error(`cannot read style ${id}`);
    return {id, game, version, summary};
  });
  const beds = Object.values(json(r.beds)).map(b => ({
    id: b.bed, game: b.game ?? b.bed.split('-')[0], durationSeconds: b.durationSeconds, revealSeconds: b.revealSeconds,
    title: b.title, artist: b.artist ?? null, license: b.license, sourceUrl: b.page ?? null,
    // The owner's six Gemini beds stay local (not in the public repo) and are retired for new batches.
    retired: b.license === 'owner-supplied',
  })).sort((a, b) => a.id.localeCompare(b.id));
  return {templates: templates.map(t => ({...t, ...timingOf(t.format)})), styles, beds};
}

function story(engine) {
  const reg = json(engine.registries.models);
  if (reg.registryVersion !== 1) throw new Error('engines/story/registry.json: registryVersion must be 1');
  return {
    routes: reg.routes, defaultModels: reg.defaultModels, tierDefaults: reg.tierDefaults, fallbackOrder: reg.fallbackOrder,
    videoModels: reg.videoModels.map(m => ({id: m.model_id, name: m.display_name, provider: m.provider, tier: m.tier,
      costPerSecondUsd: m.cost_per_second ?? null, maxResolution: m.max_resolution, maxDurationSeconds: m.max_duration_sec,
      audio: m.has_audio, referenceImages: m.has_reference_images, description: m.description})),
  };
}

export function buildCatalog() {
  const {studio, projects} = loadStudio();
  const engines = studio.engines.map(e => ({
    id: e.id, name: e.name, summary: e.summary, kitVersion: e.kitVersion, routes: e.routes,
    ...(e.id === 'motion' ? motion(e) : story(e)),
  }));
  const formats = new Set(engines.find(e => e.id === 'motion').templates.map(t => t.format));
  const routes = new Set(engines.find(e => e.id === 'story').routes.map(r => r.id));
  const out = Object.values(projects).sort((a, b) => a.order - b.order).map(p => {
    for (const f of p.formats) {
      if (f.engine === 'motion' && !formats.has(f.id)) throw new Error(`${p.id}/${f.id}: the motion engine has no template for it`);
      if (f.engine === 'story' && !routes.has(f.route)) throw new Error(`${p.id}/${f.id}: the story engine has no route ${f.route}`);
    }
    return {id: p.id, name: p.name, priority: p.priority, order: p.order, summary: p.summary, contractSchemaVersion: p.contract.schemaVersion,
      formats: p.formats, ...(p.games ? {games: p.games} : {}), link: p.link, callToAction: p.callToAction, captions: p.captions,
      budget: p.budget, mix: p.mix, checks: p.checks.map(c => ({id: c.id, name: c.name}))};
  });
  return {catalogVersion: 1, studio: {name: studio.name, summary: studio.summary, flow: studio.flow},
    projects: out, engines, channels: studio.channels};
}

const body = JSON.stringify(buildCatalog(), null, 1) + '\n';
if (process.argv.includes('--check')) {
  if (!existsSync(OUT) || readFileSync(OUT, 'utf8') !== body) {
    console.error('publisher/catalog.json is stale: run node tools/export-catalog.mjs and commit it.');
    process.exit(1);
  }
  console.log('publisher/catalog.json matches its sources.');
} else {
  writeFileSync(OUT, body);
  console.log(`publisher/catalog.json: ${body.length} bytes`);
}
