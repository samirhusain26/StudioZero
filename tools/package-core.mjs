// Pure core of the shared packager (no Node or browser APIs): used by tools/package.mjs on the Mac and by the Studio's
// browser packaging (publisher/ui). The project module turns render.json documents into episodes; this file checks the
// render.json inputs and writes the batch.json text (contract v1 or v2, contract/BATCH_CONTRACT.md).
import {checkRender, NEEDS_ATTRIBUTION, TMDB_NOTICE} from './render-json-core.mjs';

export const BATCH_ID = /^\d{4}-\d{2}-[a-z0-9-]+$/;
export const CONTRACT_VERSIONS = [1, 2];

/** Errors for one render.json that the packager is about to read from <jobs>/<folder>/render.json. */
export function renderErrors(render, {folder, project, known, schemaVersion = project.contract.schemaVersion}) {
  const errors = checkRender(render, {projects: known});
  if (render?.episodeId !== folder) errors.push(`episodeId ${render?.episodeId} differs from its folder`);
  if (render?.project !== project.id) errors.push(`project ${render?.project}, expected ${project.id}`);
  if (schemaVersion >= 2) (render?.credits ?? []).forEach((c, i) => {
    if (c?.license === 'unknown') errors.push(`credits[${i}] (${c.title}) has an unknown licence; contract v2 refuses it`);
  });
  return errors;
}

/** The project's packager must exist and target a contract version this code writes. */
export function checkProject(project, schemaVersion = project.contract.schemaVersion) {
  if (!project.packager) throw new Error(`${project.id} has no packager yet (project.json "packager")`);
  if (!CONTRACT_VERSIONS.includes(schemaVersion)) throw new Error(`${project.id}: contract v${schemaVersion} is not supported`);
}

/** Texts every posting platform must carry (contract v2 attribution rule; same as library_contract.required_attributions). */
export function requiredAttributions(credits) {
  const texts = [];
  for (const c of credits ?? []) {
    if (NEEDS_ATTRIBUTION.includes(c?.license) && typeof c.attribution === 'string' && c.attribution.trim()) texts.push(c.attribution.trim());
    if (c?.license === 'TMDB') texts.push(TMDB_NOTICE);
  }
  return [...new Set(texts)].filter((t, _, all) => !all.some(o => o !== t && o.includes(t)));
}

/** v2 render block from a render.json document and the sha256 of its file. */
export function renderBlock(render, renderSha256) {
  if (!/^[0-9a-f]{64}$/.test(renderSha256 ?? '')) throw new Error(`${render.episodeId}: no renderSha256`);
  return {engine: render.engine, route: render.route, renderer: render.job?.renderer ?? null, kitVersion: render.kitVersion,
    renderSha256, models: render.models.map(m => ({role: m.role, id: m.id})), costUsd: render.costUsd};
}

/** batch.json text: generator stamp, the project's batch fields and episodes, in contract field order. */
export function batchDocument({project, batchId, createdAt, commit, dirty, packaged, schemaVersion = project.contract.schemaVersion}) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(createdAt) || !/^[0-9a-f]{40}$/.test(commit)) throw new Error('bad --created-at or --commit');
  const out = schemaVersion === 1
    ? {schemaVersion, batchId, createdAt, generator: {repoCommit: commit, dirty, ...packaged.generator}, ...packaged.fields, episodes: packaged.episodes}
    : {schemaVersion, batchId, createdAt, project: project.id, generator: {repoCommit: commit, dirty},
      styleRecipes: packaged.fields.styleRecipes, projectData: packaged.fields.projectData, episodes: packaged.episodes};
  return JSON.stringify(out, null, 2) + '\n';
}
