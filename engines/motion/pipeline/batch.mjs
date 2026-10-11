// Write library/<batch>/batch.json exactly per contract/BATCH_CONTRACT.md (schemaVersion 1) from validated jobs.
//   node engines/motion/pipeline/batch.mjs --batch=<batchId> [--set=questions-<set> | --set=<path/to/set.mjs>] [--dir=<batch dir>] [--dry]
// experimentId, variantId, reviewer text and the fact-check file come from the set's CONFIG; default set
// questions-2026-10 (the frozen regression set). Every episode needs an independent source check result, and a
// concern/fail needs a written resolution.
// Captions, titles, alt text, polls and first comments are deterministic templates filled from episode metadata.
// The answer appears only as one item of the complete choice list (the contract's spoiler rule); answerReply is null.
import {readFileSync, writeFileSync, existsSync, readdirSync} from 'node:fs';
import {resolve, relative} from 'node:path';
import {execFileSync} from 'node:child_process';
import {ROOT, STUDIO, loadSet, bedPool} from './lib.mjs';

const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, v = true] = a.replace(/^--/, '').split('='); return [k, v]; }));
const batch = args.batch;
const BATCH = resolve(ROOT, args.dir ?? `library/${batch}`);
if (existsSync(resolve(BATCH, 'READY_FOR_UPLOAD'))) throw new Error(`${batch} is finalized; batch.json is immutable.`);
const SET = await loadSet(args.set ?? 'questions-2026-10');
const CONFIG = SET.config;
if (!args.dry && !CONFIG.batches.includes(batch)) throw new Error(`${batch} is not in ${SET.name} CONFIG.batches (${CONFIG.batches.join(', ')}); pass --set=`);
const doc = JSON.parse(readFileSync(SET.checkedPath, 'utf8'));
const byKey = Object.fromEntries(doc.questions.map(q => [q.key, q]));
const beds = JSON.parse(readFileSync(resolve(STUDIO, 'public/episodes/music/beds.json'), 'utf8'));
const verPath = resolve(ROOT, CONFIG.verification ?? resolve(BATCH, 'review/source-verification.json'));
if (!existsSync(verPath) && !args.dry) throw new Error(`no independent source check: ${relative(ROOT, verPath)} (run the fact-checker first)`);
const verification = existsSync(verPath) ? JSON.parse(readFileSync(verPath, 'utf8')) : {results: []};
const verified = Object.fromEntries(verification.results.map(r => [r.key, r]));
const git = (...a) => execFileSync('git', ['-C', ROOT, ...a]).toString().trim();

const SITE = 'https://www.scalargame.com', CAMPAIGN = 'social_library_v1';
const LIMIT = {instagram: 2200, facebook: 2200, threads: 500, x: 280, bluesky: 300, tiktok: 2200};
const HASHTAGS = {
  scalar: ['#geography', '#quiz', '#countries', '#trivia', '#scalargame'],
  continuum: ['#geography', '#quiz', '#worldfacts', '#trivia', '#scalargame'],
  whenabouts: ['#history', '#quiz', '#trivia', '#onthisday', '#scalargame'],
  tectonic: ['#geography', '#maps', '#quiz', '#trivia', '#scalargame'],
};
const link = (ep, platform) => `${SITE}/${ep.game}?${new URLSearchParams({utm_source: platform, utm_medium: 'organic_social', utm_campaign: CAMPAIGN, utm_content: ep.episodeId})}`;
const measure = (ep, platform, text) => {
  const final = text.replaceAll('{link}', link(ep, platform));
  return platform === 'x' ? final.replace(/https?:\/\/\S+/g, '').length + 23 * (final.match(/https?:\/\/\S+/g) ?? []).length : [...final].length;
};

/** Spoiler-safe building blocks. `choices` is the only place the answer may appear. */
function parts(q) {
  const list = q.choices.map(c => `${c.key}) ${c.label}`).join('  ');
  const metricQ = q.metric?.id === 'population' ? 'Which has more people?' : 'Which is bigger by area?';
  switch (q.format) {
    case 'progressive-clues': return {lead: `Three clues. One country.\n${q.clues.map((c, i) => `${i + 1}. ${c}`).join('\n')}`,
      short: `Three clues, one country: ${q.clues.join(' · ')}.`, choices: list, title: 'Three clues, one country. Which is it?', poll: 'Which country fits all three clues?',
      alt: 'Animated geography quiz from Scalargame: three clues about a mystery country appear one by one on index cards, a counter shows how many countries still fit, then three answer choices. The answer is revealed and explained at the end.'};
    case 'candidate-elimination': return {lead: `Only one of these countries fits every clue:\n${q.clues.map((c, i) => `${i + 1}. ${c}`).join('\n')}`,
      short: `Only one fits every clue: ${q.clues.join(' · ')}.`, choices: list, title: 'Only one of these countries fits every clue', poll: 'Which country fits all three clues?',
      alt: 'Animated geography quiz from Scalargame: three candidate countries and three clues. Following a pause, the clues rule candidates out one by one and the answer is revealed and explained.'};
    case 'head-to-head': return {lead: metricQ, short: metricQ, choices: list, title: `${metricQ.replace('?', ':')} ${q.choices.map(c => c.label).join(' or ')}?`, poll: metricQ,
      alt: `Animated quiz from Scalargame comparing two countries by ${q.metric.id === 'population' ? 'population' : 'area'}. Following a pause, bar charts on one scale reveal the answer, with ${q.metric.year} World Bank figures.`};
    case 'missing-slot': return {lead: q.question, short: q.question, choices: list, title: q.question, poll: q.question,
      alt: `Animated quiz from Scalargame: a ranking ladder of two countries by ${q.metric.id === 'population' ? 'population' : 'area'} and a third country to place in that ranking. The answer and the ${q.metric.year} World Bank figures are revealed at the end.`};
    case 'guess-the-year': return {lead: `Guess the year: ${q.prompt}.`, short: `Guess the year: ${q.prompt}.`, choices: list, title: `Guess the year: ${q.prompt}`, poll: `What year: ${q.prompt}?`,
      alt: 'Animated history quiz from Scalargame: an event card and three possible years on a timeline. Following a pause, a rolling year counter reveals the answer with a short reviewed fact.'};
    case 'before-after': {
      const anchorYear = q.anchor.year < 0 ? `${-q.anchor.year} BCE` : q.anchor.year < 1000 ? `${q.anchor.year} CE` : String(q.anchor.year);
      const bba = `${q.prompt}: A) before or B) after ${q.anchorPrompt}?`;
      return {lead: bba, short: bba, choices: null, title: `${q.prompt}: before or after ${q.anchorPrompt}?`, poll: `${q.prompt}. Compared with when ${q.anchorPrompt} (${anchorYear}), was it…`,
        alt: `Animated history quiz from Scalargame: an event card and a timeline with one dated anchor event (${q.anchorPrompt}, ${anchorYear}). Following a pause, the event slides to its place on the timeline and its date is shown.`};
    }
    case 'missing-country': return {lead: 'One country is missing from this map. Which one fills the gap?', short: 'One country is missing from this map. Which one fills the gap?', choices: list,
      title: 'One country is missing from this map. Which one?', poll: 'Which country fills the gap?',
      alt: 'Animated map quiz from Scalargame: neighboring countries drift into place around an empty, outlined gap, then three answer choices. Following a pause, the missing country drops into place and the map zooms out.'};
    case 'neighbor-clues': {
      const names = q.shown.map(s => s.label);
      const intro = q.allNeighbors ? 'Its only land neighbors' : 'It borders';
      return {lead: `${intro}: ${names.join(', ')}. Which country is it?`, short: `${intro}: ${names.join(', ')}. Which country?`, choices: list,
        title: `${intro}: ${names.join(', ')}. Which country?`, poll: 'Which country borders all of these?',
        alt: `Animated map quiz from Scalargame: three neighboring countries appear as clue cards (${names.join(', ')}), then three answer choices. Following a pause, the cards move to their true positions on a map and the answer is revealed.`};
    }
  }
  throw new Error(`no caption template for ${q.format}`);
}

function captions(ep, q) {
  const p = parts(q), tags = HASHTAGS[q.game].join(' ');
  const ask = p.choices ? `${p.choices} — comment your letter.` : 'Comment A or B.';
  const body = p.choices ? `${p.lead}\n\n${ask}` : `${p.lead}\n\n${ask}`;
  const variants = {
    instagram: [`${body}\n\nThe answer is at the end of the video. Play a new puzzle at scalargame.com (link in bio).\n\n${tags}`],
    tiktok: [`${body}\n\nThe answer is at the end of the video. Play a new puzzle at scalargame.com\n\n${tags}`],
    facebook: [`${body}\n\nThe answer is at the end. Play a new puzzle: {link}\n\n${tags}`],
    threads: [`${body}\n\nPlay a new puzzle: {link}`, `${p.short}\n${ask}\n{link}`],
    // Last resort for short limits: the choices stay in the video only (no choice list → no answer in the text).
    x: [`${p.short} ${ask} {link}`, `${p.choices ? `${p.lead.split('\n')[0]} ${ask}` : `${p.short} ${ask}`} {link}`, `${p.title} Choices in the video — comment your letter. {link}`],
    bluesky: [`${p.short}\n${ask}\n{link}`, `${p.choices ? `${p.lead.split('\n')[0]}\n${ask}` : `${p.short}\n${ask}`}\n{link}`, `${p.title}\nChoices in the video — comment your letter.\n{link}`],
  };
  const out = {};
  for (const [platform, options] of Object.entries(variants)) {
    out[platform] = options.find(t => measure(ep, platform, t) <= LIMIT[platform]);
    if (!out[platform]) throw new Error(`${ep.episodeId}: no ${platform} caption fits ${LIMIT[platform]}`);
  }
  const youtubeLink = `${SITE}/${q.game}?${new URLSearchParams({utm_source: 'youtube', utm_medium: 'organic_social', utm_campaign: CAMPAIGN, utm_content: ep.episodeId})}`;
  let title = `${p.title} #shorts`;
  if (title.length > 100) title = `${p.title.slice(0, 100 - 9).trimEnd()}… #shorts`;
  const youtube = {title, description: `${body}\n\nThe answer is revealed at the end. Play a new puzzle at ${youtubeLink}\n\n${tags}`};
  const comment = p.choices ? `${p.choices} — comment your letter` : `A) Before  B) After — comment your letter`;
  return {captions: out, youtube, altText: p.alt, hashtags: HASHTAGS[q.game], poll: {question: p.poll, options: q.choices.map(c => c.poll ?? c.label)},
    firstComment: {instagram: comment, threads: comment, bluesky: null, x: null}};
}

const styleRecipes = new Map();
const recipeOf = id => {
  const src = readFileSync(resolve(STUDIO, `src/episodes/styles/${id}.ts`), 'utf8');
  const summary = src.match(/summary:\s*(['"`])([\s\S]*?)\1\s*,/)?.[2];
  const version = Number(src.match(/version:\s*(\d+)/)?.[1]);
  const game = src.match(/game:\s*'(\w+)'/)?.[1];
  if (!summary || !version || !game) throw new Error(`cannot read style recipe ${id}`);
  return {styleId: id, game, version, summary};
};

const episodes = [];
const jobs = resolve(BATCH, 'review/jobs');
// --dry: metadata for every main question with stand-in media fields, to check captions against the contract early.
const entries = args.dry
  ? doc.questions.filter(q => !q.spare).map(q => {
      const STY = CONFIG.styles, BEDS = CONFIG.beds;
      const id = `${q.game}-dry-${String(doc.questions.indexOf(q)).padStart(3, '0')}`;
      return [id, {questionKey: q.key, revision: 1, styleId: STY[q.game], props: {music: {bed: `${bedPool(BEDS, q, null, beds)[0]}.m4a`}}},
        {state: 'validated', video: {sha256: '0'.repeat(64), bytes: 1, durationSeconds: 22, width: 1080, height: 1920, fps: '30/1', videoCodec: 'h264', audioCodec: 'aac'}, cover: {sha256: '0'.repeat(64), bytes: 1}}];
    })
  : readdirSync(jobs).sort().map(id => [id, JSON.parse(readFileSync(resolve(jobs, id, 'input.json'), 'utf8')),
      existsSync(resolve(jobs, id, 'status.json')) ? JSON.parse(readFileSync(resolve(jobs, id, 'status.json'), 'utf8')) : null]);
for (const [id, input, status] of entries) {
  if (status?.state !== 'validated') throw new Error(`${id}: job not validated (${status?.state ?? 'no status'}); render first`);
  const q = byKey[input.questionKey];
  if (!styleRecipes.has(input.styleId)) styleRecipes.set(input.styleId, recipeOf(input.styleId));
  const ep = {episodeId: id, game: q.game};
  const pub = captions(ep, q);
  const choices = q.choices.map(c => ({key: c.key, label: c.label}));
  const aliases = q.format === 'missing-slot' ? [q.choices.find(c => c.key === q.answerKey).poll] : [];
  const answer = q.format === 'missing-slot' ? q.choices.find(c => c.key === q.answerKey).label : q.answer;
  const bed = beds[input.props.music.bed.replace(/\.m4a$/, '')];
  const v = verified[q.key];
  if (!args.dry && !v) throw new Error(`${id}: ${q.key} has no result in ${relative(ROOT, verPath)}`);
  if (!args.dry && v.status !== 'pass' && !v.resolution) throw new Error(`${id}: ${q.key} source check is ${v.status} with no written resolution`);
  episodes.push({
    episodeId: id, questionId: q.questionId, revision: input.revision, game: q.game, format: q.format, language: 'en',
    difficulty: q.difficulty, styleId: input.styleId, experimentId: CONFIG.experimentId, variantId: CONFIG.variantId ?? null,
    creative: {
      hook: q.hook, question: q.prompt && q.format === 'before-after' ? `${q.prompt}. ${q.question}` : q.question,
      clues: q.clues ?? (q.shown ? q.shown.map(s => s.label) : []), choices, answer, answerAliases: aliases, explanation: q.explanation,
    },
    evidence: {
      sources: q.evidence.sources,
      checks: {...q.evidence.checks, uniqueAnswer: true, snapshotId: doc.snapshotId, questionsHash: doc.questionsHash,
        independentSourceCheck: v ? {status: v.status, resolution: v.resolution ?? null, report: relative(ROOT, verPath)} : null,
        rationale: q.rationale, ...(q.editorialNote ? {editorialNote: q.editorialNote} : {}), ...(q.sensitiveReview ? {sensitiveReview: q.sensitiveReview} : {})},
      reviewer: CONFIG.reviewer,
    },
    music: {trackId: `${bed.trackId}:${bed.bed}`, sha256: bed.sha256, license: bed.license},
    video: {file: `videos/${id}.mp4`, sha256: status.video.sha256, bytes: status.video.bytes, durationSeconds: status.video.durationSeconds,
      width: status.video.width, height: status.video.height, fps: status.video.fps, videoCodec: status.video.videoCodec, audioCodec: status.video.audioCodec},
    cover: {file: `covers/${id}.jpg`, sha256: status.cover.sha256, bytes: status.cover.bytes},
    publication: {deepLink: `/${q.game}`, utmCampaign: CAMPAIGN, ...pub,
      credits: ['scalar', 'tectonic'].includes(q.game) ? ['Map data: Natural Earth'] : [], answerReply: null},
    eligibility: {status: 'qa-passed', notBefore: null, reviewBy: q.reviewBy, expiresAt: null},
  });
}

const commit = git('rev-parse', 'HEAD');
const dirty = git('status', '--porcelain').length > 0;
const out = {
  schemaVersion: 1, batchId: batch, createdAt: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
  generator: {repoCommit: commit, dirty, assetKitVersion: 'kit-1'},
  sourceSnapshotHash: doc.snapshotHash, styleRecipes: [...styleRecipes.values()], episodes,
};
if (args.dry) {
  const {mkdirSync} = await import('node:fs');
  mkdirSync(resolve(ROOT, 'library/_dev'), {recursive: true});
  writeFileSync(resolve(ROOT, 'library/_dev/batch-dry.json'), JSON.stringify(out, null, 2) + '\n');
  console.log('dry metadata: library/_dev/batch-dry.json');
} else writeFileSync(resolve(BATCH, 'batch.json'), JSON.stringify(out, null, 2) + '\n');
console.log(JSON.stringify({batch, episodes: episodes.length, dirty, commit: commit.slice(0, 7)}));
