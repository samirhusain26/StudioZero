// Pure core of the shared packager (no Node or browser APIs): used by tools/package.mjs on the Mac and by the Studio's
// browser packaging (publisher/ui). The project module turns render.json documents into episodes; this file checks the
// render.json inputs and writes the batch.json text.
import {checkRender} from './render-json-core.mjs';

export const BATCH_ID = /^\d{4}-\d{2}-[a-z0-9-]+$/;

/** Errors for one render.json that the packager is about to read from <jobs>/<folder>/render.json. */
export function renderErrors(render, {folder, project, known}) {
  const errors = checkRender(render, {projects: known});
  if (render?.episodeId !== folder) errors.push(`episodeId ${render?.episodeId} differs from its folder`);
  if (render?.project !== project.id) errors.push(`project ${render?.project}, expected ${project.id}`);
  return errors;
}

/** The project's packager must exist and target the contract version this code writes (v1 until Phase 4). */
export function checkProject(project) {
  if (!project.packager) throw new Error(`${project.id} has no packager yet (project.json "packager")`);
  if (project.contract.schemaVersion !== 1) throw new Error(`${project.id} needs contract v${project.contract.schemaVersion} (Phase 4)`);
}

/** batch.json text: generator stamp, the project's batch fields and episodes, in contract field order. */
export function batchDocument({project, batchId, createdAt, commit, dirty, packaged}) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(createdAt) || !/^[0-9a-f]{40}$/.test(commit)) throw new Error('bad --created-at or --commit');
  const out = {
    schemaVersion: project.contract.schemaVersion, batchId, createdAt,
    generator: {repoCommit: commit, dirty, ...packaged.generator}, ...packaged.fields, episodes: packaged.episodes,
  };
  return JSON.stringify(out, null, 2) + '\n';
}
