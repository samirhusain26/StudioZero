// Originals' packager core (pure: no Node or browser APIs): contract v2 episodes from the story engine's render.json
// files (recap and series routes) and the batch's review file (review/originals.json: the reviewer's checks per
// episode). Captions, titles and alt text are deterministic templates from render.json's job facts and project.json;
// every required attribution (TMDB notice, Wikipedia licence, CC BY) is written into each caption and the YouTube
// description (contract v2 attribution rule). A platform whose limit cannot hold the caption with its attribution
// gets no caption (it does not post) and a warning.
import {renderBlock, requiredAttributions} from '../../tools/package-core.mjs';

const slug = text => String(text).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
const POSTS = ['instagram', 'facebook', 'threads', 'x', 'bluesky', 'tiktok'];
const LONG = ['instagram', 'facebook', 'tiktok'];
const CHECKS = ['rights', 'garbage', 'visualQa'];

/** The facts a caption is built from, per route. */
function facts(render) {
  const job = render.job ?? {};
  if (render.route === 'recap') {
    const year = /^\d{4}$/.test(String(job.year ?? '')) ? Number(job.year) : null;
    const title = job.title ?? job.input;
    return {format: job.format ?? 'movie-recap', title, year, contentKey: slug(`${title} ${year ?? ''}`),
      hook: `${title}${year ? ` (${year})` : ''} in under a minute.`, alt: `A narrated recap of ${title}${year ? ` (${year})` : ''} over stock footage, with captions.`,
      subject: {kind: 'movie', title, year}, series: null,
      sources: [job.plotUrl && {title: `Plot source: ${job.plotSource ?? 'reference'}`, url: job.plotUrl},
        job.tmdbId && {title: `${title} on TMDB`, url: `https://www.themoviedb.org/movie/${job.tmdbId}`}].filter(Boolean)};
  }
  const n = job.episodeNumber;
  const series = slug(job.projectDir ?? job.projectTitle);
  return {format: job.format ?? 'animated-short', title: job.projectTitle, year: null, contentKey: `${series}-ep${n}`,
    hook: `${job.projectTitle}, episode ${n}${job.episodeTitle ? `: ${job.episodeTitle}` : ''}.`,
    alt: `An AI-animated short: ${job.projectTitle}, episode ${n}.${job.logline ? ` ${job.logline}` : ''}`.slice(0, 1000),
    subject: {kind: 'original', title: job.projectTitle, year: null}, series: {seriesId: series, episode: n}, sources: []};
}

/**
 * v2 batch fields from story render.json documents (sorted by episodeId). Returns {generator, fields, episodes,
 * warnings}. `review` is review/originals.json: {reviewer, experimentId?, episodes: {<episodeId>: {checks: {rights,
 * garbage, visualQa}, hook?, reviewBy?}}}; every check must be true. `renderHashes` maps episodeId → sha256 of its
 * render.json file. `limits` are the channel caption limits from studio.json.
 */
export function originalsEpisodes({renders, project, studio, review, renderHashes}) {
  const limit = Object.fromEntries(studio.channels.map(c => [c.id, c.captionLimit]));
  const titleLimit = studio.channels.find(c => c.id === 'youtube').titleLimit;
  const formats = new Set(project.formats.map(f => f.id));
  const warnings = [];
  const episodes = renders.map(render => {
    const id = render.episodeId;
    const entry = review?.episodes?.[id];
    if (!entry) throw new Error(`${id}: no entry in review/originals.json`);
    const failed = CHECKS.filter(k => entry.checks?.[k] !== true);
    if (failed.length) throw new Error(`${id}: review checks not passed: ${failed.join(', ')}`);
    const f = facts(render);
    if (!formats.has(f.format)) throw new Error(`${id}: format ${f.format} is not an Originals format`);
    const hook = entry.hook ?? f.hook;
    const tags = project.captions.hashtags[f.format] ?? [];
    const engage = `${project.callToAction.engage}.`;
    const credit = requiredAttributions(render.credits).join('\n');
    const att = credit ? `\n\n${credit}` : '';
    const captions = {};
    for (const p of POSTS) {
      const text = LONG.includes(p) ? `${hook}\n\n${engage}${att}\n\n${tags.join(' ')}` : `${hook} ${engage}${att}`;
      captions[p] = [...text].length <= limit[p] ? text : null;
      if (!captions[p]) warnings.push(`${id}: no ${p} caption (${[...text].length} > ${limit[p]} characters with the attribution)`);
    }
    const suffix = project.captions.youtubeTitleSuffix;
    const title = `${hook.replace(/\.$/, '')}`.slice(0, titleLimit - suffix.length) + suffix;
    const retrieved = render.createdAt.slice(0, 10);
    return {
      episodeId: id, contentId: `originals:${f.format}:${f.contentKey}`, revision: entry.revision ?? 1, format: f.format,
      language: project.captions.language, render: renderBlock(render, renderHashes[id]),
      experimentId: review.experimentId ?? null, variantId: null, tags: [],
      video: {file: `videos/${id}.mp4`, sha256: render.video.sha256, bytes: render.video.bytes, durationSeconds: render.video.durationSeconds,
        width: render.video.width, height: render.video.height, fps: render.video.fps, videoCodec: render.video.videoCodec, audioCodec: render.video.audioCodec},
      cover: {file: `covers/${id}.jpg`, sha256: render.cover.sha256, bytes: render.cover.bytes},
      link: null,
      publication: {captions, youtube: {title, description: `${hook}\n\n${engage}${att}\n\n${tags.join(' ')}`}, altText: f.alt,
        hashtags: tags, poll: null, firstComment: null, answerReply: null},
      credits: render.credits, disclosure: render.disclosure,
      eligibility: {status: 'qa-passed', notBefore: null, reviewBy: entry.reviewBy ?? null, expiresAt: null},
      projectData: {subject: f.subject, sources: f.sources.map(s => ({...s, retrieved})),
        checks: Object.fromEntries(CHECKS.map(k => [k, true])), reviewer: review.reviewer, series: f.series},
    };
  });
  return {generator: {}, fields: {styleRecipes: [], projectData: null}, episodes, warnings};
}
