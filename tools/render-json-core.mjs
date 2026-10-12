// Pure render.json check (no Node or browser APIs), shared by tools/render-json.mjs, tools/package.mjs and the Studio's
// browser packaging (publisher/ui). Format: tools/RENDER_JSON.md.
export const ROLES = ['llm', 'tts', 'image', 'video', 'music', 'asr'];
export const KINDS = ['footage', 'image', 'poster', 'music', 'sfx', 'font', 'voice', 'data', 'text', 'model'];
export const LICENSES = ['CC0-1.0', 'CC-BY-4.0', 'CC-BY-SA-4.0', 'OFL-1.1', 'Pexels', 'Pixabay', 'TMDB', 'Wikipedia-CC-BY-SA', 'owner', 'generated', 'public-domain', 'unknown'];
export const NEEDS_ATTRIBUTION = ['CC-BY-4.0', 'CC-BY-SA-4.0', 'TMDB', 'Wikipedia-CC-BY-SA'];
export const TMDB_NOTICE = 'This product uses the TMDB API but is not endorsed or certified by TMDB';
export const AI_KINDS = ['script', 'voice', 'image', 'video', 'music', 'sfx'];
const GENERATIVE = ['llm', 'tts', 'image', 'video', 'music'];

const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const isStr = v => typeof v === 'string' && v.trim() !== '';
const isHex = v => typeof v === 'string' && /^[0-9a-f]{64}$/.test(v);
const isInt = v => Number.isInteger(v) && v > 0;
const relFile = v => isStr(v) && !v.startsWith('/') && !v.split(/[\\/]/).includes('..');

/** Returns a list of error strings ([] when valid). `projects`, when given, is the set of known project ids. */
export function checkRender(doc, {projects} = {}) {
  const e = [];
  if (!isObj(doc)) return ['not a JSON object'];
  if (doc.renderJsonVersion !== 1) e.push('renderJsonVersion must be 1');
  if (!['motion', 'story'].includes(doc.engine)) e.push('engine must be motion or story');
  if (doc.engine === 'motion' && doc.route !== null) e.push('route must be null for motion');
  if (doc.engine === 'story' && !['recap', 'series'].includes(doc.route)) e.push('route must be recap or series for story');
  if (!isStr(doc.kitVersion)) e.push('kitVersion is required');
  if (!isStr(doc.project) || (projects && !projects.has(doc.project))) e.push(`unknown project ${JSON.stringify(doc.project)}`);
  if (typeof doc.episodeId !== 'string' || !/^[a-z0-9-]{1,80}$/.test(doc.episodeId)) e.push('episodeId must match [a-z0-9-]{1,80}');
  if (typeof doc.createdAt !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(doc.createdAt)) e.push('createdAt must be UTC YYYY-MM-DDTHH:MM:SSZ');
  if (!isObj(doc.job)) e.push('job must be an object');
  const v = doc.video;
  if (!isObj(v)) e.push('video must be an object');
  else {
    if (!relFile(v.file)) e.push('video.file must be a relative path inside the render folder');
    if (!isHex(v.sha256)) e.push('video.sha256 must be 64 hex characters');
    if (!isInt(v.bytes)) e.push('video.bytes must be a positive integer');
    if (!(typeof v.durationSeconds === 'number' && v.durationSeconds > 0)) e.push('video.durationSeconds must be > 0');
    if (!isInt(v.width) || !isInt(v.height)) e.push('video.width/height must be positive integers');
    if (typeof v.fps !== 'string' || !/^\d+\/\d+$/.test(v.fps)) e.push('video.fps must be num/den');
    if (!isStr(v.videoCodec)) e.push('video.videoCodec is required');
    if (v.audioCodec !== null && !isStr(v.audioCodec)) e.push('video.audioCodec must be a string or null');
  }
  if (doc.cover !== null) {
    const c = doc.cover;
    if (!isObj(c) || !relFile(c.file) || !isHex(c.sha256) || !isInt(c.bytes)) e.push('cover must be null or {file, sha256, bytes}');
  }
  if (!Array.isArray(doc.models)) e.push('models must be a list');
  else doc.models.forEach((m, i) => { if (!isObj(m) || !ROLES.includes(m.role) || !isStr(m.id)) e.push(`models[${i}] must be {role in ${ROLES.join('|')}, id}`); });
  if (!(typeof doc.costUsd === 'number' && Number.isFinite(doc.costUsd) && doc.costUsd >= 0)) e.push('costUsd must be a number >= 0');
  if (typeof doc.costEstimated !== 'boolean') e.push('costEstimated must be a boolean');
  if (!Array.isArray(doc.credits)) e.push('credits must be a list');
  else doc.credits.forEach((c, i) => {
    const at = `credits[${i}]`;
    if (!isObj(c)) return e.push(`${at} must be an object`);
    if (!KINDS.includes(c.kind)) e.push(`${at}.kind must be one of ${KINDS.join(', ')}`);
    if (!isStr(c.title)) e.push(`${at}.title is required`);
    if (c.creator !== null && !isStr(c.creator)) e.push(`${at}.creator must be text or null`);
    if (c.sourceUrl !== null && !(typeof c.sourceUrl === 'string' && /^https:\/\/\S+$/.test(c.sourceUrl))) e.push(`${at}.sourceUrl must be https or null`);
    if (!LICENSES.includes(c.license)) e.push(`${at}.license must be one of ${LICENSES.join(', ')}`);
    if (c.attribution !== null && !isStr(c.attribution)) e.push(`${at}.attribution must be text or null`);
    if (NEEDS_ATTRIBUTION.includes(c.license) && !isStr(c.attribution)) e.push(`${at}: ${c.license} needs attribution text`);
    if (c.license === 'TMDB' && !String(c.attribution ?? '').includes(TMDB_NOTICE)) e.push(`${at}: TMDB attribution must contain the TMDB notice`);
    if (c.sha256 !== null && !isHex(c.sha256)) e.push(`${at}.sha256 must be 64 hex characters or null`);
  });
  const d = doc.disclosure;
  if (!isObj(d)) e.push('disclosure must be an object');
  else {
    if (typeof d.aiGenerated !== 'boolean') e.push('disclosure.aiGenerated must be a boolean');
    if (!Array.isArray(d.aiKinds) || d.aiKinds.some(k => !AI_KINDS.includes(k))) e.push(`disclosure.aiKinds must be a subset of ${AI_KINDS.join(', ')}`);
    else if (d.aiGenerated !== (d.aiKinds.length > 0)) e.push('disclosure.aiGenerated must be true exactly when aiKinds is non-empty');
    if (typeof d.realisticSynthetic !== 'boolean') e.push('disclosure.realisticSynthetic must be a boolean');
    if (!isStr(d.note)) e.push('disclosure.note is required');
    if (Array.isArray(doc.models) && doc.models.some(m => GENERATIVE.includes(m?.role)) && d.aiGenerated !== true) e.push('disclosure.aiGenerated must be true when a generative model is listed');
  }
  return e;
}
