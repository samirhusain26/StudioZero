// Scalargame's packager core (pure: no Node or browser APIs), shared by package.mjs on the Mac and the Studio's
// browser packaging (publisher/ui): contract v1 episodes from the motion engine's render.json files, the checked
// question set and this project's caption rules (project.json). The caller loads every input.
// Captions, titles, alt text, polls and first comments are deterministic templates filled from episode metadata.
// The answer appears only as one item of the complete choice list (the contract's spoiler rule); answerReply is null.

/** Pieces of every platform text, from the project manifest and the channel limits in studio.json. */
function rules(project, studio) {
  const {site, utm} = project.link;
  return {
    SITE: site, CAMPAIGN: utm.campaign, HASHTAGS: project.captions.hashtags, TITLE_SUFFIX: project.captions.youtubeTitleSuffix,
    LIMIT: Object.fromEntries(studio.channels.map(c => [c.id, c.captionLimit])),
    TITLE_LIMIT: studio.channels.find(c => c.id === 'youtube').titleLimit,
  };
}

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

function captions(R, ep, q) {
  const link = platform => `${R.SITE}/${ep.game}?${new URLSearchParams({utm_source: platform, utm_medium: 'organic_social', utm_campaign: R.CAMPAIGN, utm_content: ep.episodeId})}`;
  const measure = (platform, text) => {
    const final = text.replaceAll('{link}', link(platform));
    return platform === 'x' ? final.replace(/https?:\/\/\S+/g, '').length + 23 * (final.match(/https?:\/\/\S+/g) ?? []).length : [...final].length;
  };
  const p = parts(q), tags = R.HASHTAGS[q.game].join(' ');
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
    out[platform] = options.find(t => measure(platform, t) <= R.LIMIT[platform]);
    if (!out[platform]) throw new Error(`${ep.episodeId}: no ${platform} caption fits ${R.LIMIT[platform]}`);
  }
  let title = `${p.title}${R.TITLE_SUFFIX}`;
  if (title.length > R.TITLE_LIMIT) title = `${p.title.slice(0, R.TITLE_LIMIT - 9).trimEnd()}…${R.TITLE_SUFFIX}`;
  const youtube = {title, description: `${body}\n\nThe answer is revealed at the end. Play a new puzzle at ${link('youtube')}\n\n${tags}`};
  const comment = p.choices ? `${p.choices} — comment your letter` : `A) Before  B) After — comment your letter`;
  return {captions: out, youtube, altText: p.alt, hashtags: R.HASHTAGS[q.game], poll: {question: p.poll, options: q.choices.map(c => c.poll ?? c.label)},
    firstComment: {instagram: comment, threads: comment, bluesky: null, x: null}};
}

/**
 * v1 batch fields from render.json documents (sorted by episodeId). Returns {generator, fields, episodes}.
 * `config` is the question set's CONFIG, `doc` its checked questions JSON, `verification` the independent source check
 * ({results: []} when dry), `verReport` its repo-relative path, `recipe(styleId)` the style recipe {styleId, game,
 * version, summary}.
 */
export function scalargameEpisodes({renders, project, studio, config: CONFIG, setName, doc, beds, verification, verReport, recipe, dry}) {
  const R = rules(project, studio);
  const byKey = Object.fromEntries(doc.questions.map(q => [q.key, q]));
  const verified = Object.fromEntries(verification.results.map(r => [r.key, r]));

  const styleRecipes = new Map();
  const episodes = [];
  for (const render of renders) {
    const id = render.episodeId, job = render.job;
    const q = byKey[job.contentKey];
    if (!q) throw new Error(`${id}: ${job.contentKey} is not in ${setName}`);
    if (!styleRecipes.has(job.styleId)) styleRecipes.set(job.styleId, recipe(job.styleId));
    const ep = {episodeId: id, game: q.game};
    const pub = captions(R, ep, q);
    const choices = q.choices.map(c => ({key: c.key, label: c.label}));
    const aliases = q.format === 'missing-slot' ? [q.choices.find(c => c.key === q.answerKey).poll] : [];
    const answer = q.format === 'missing-slot' ? q.choices.find(c => c.key === q.answerKey).label : q.answer;
    const bed = beds[job.musicBed];
    const v = verified[q.key];
    if (!dry && !v) throw new Error(`${id}: ${q.key} has no result in ${verReport}`);
    if (!dry && v.status !== 'pass' && !v.resolution) throw new Error(`${id}: ${q.key} source check is ${v.status} with no written resolution`);
    const video = render.video, cover = render.cover;
    episodes.push({
      episodeId: id, questionId: q.questionId, revision: job.revision, game: q.game, format: q.format, language: project.captions.language,
      difficulty: q.difficulty, styleId: job.styleId, experimentId: CONFIG.experimentId, variantId: CONFIG.variantId ?? null,
      creative: {
        hook: q.hook, question: q.prompt && q.format === 'before-after' ? `${q.prompt}. ${q.question}` : q.question,
        clues: q.clues ?? (q.shown ? q.shown.map(s => s.label) : []), choices, answer, answerAliases: aliases, explanation: q.explanation,
      },
      evidence: {
        sources: q.evidence.sources,
        checks: {...q.evidence.checks, uniqueAnswer: true, snapshotId: doc.snapshotId, questionsHash: doc.questionsHash,
          independentSourceCheck: v ? {status: v.status, resolution: v.resolution ?? null, report: verReport} : null,
          rationale: q.rationale, ...(q.editorialNote ? {editorialNote: q.editorialNote} : {}), ...(q.sensitiveReview ? {sensitiveReview: q.sensitiveReview} : {})},
        reviewer: CONFIG.reviewer,
      },
      music: {trackId: `${bed.trackId}:${bed.bed}`, sha256: bed.sha256, license: bed.license},
      video: {file: `videos/${id}.mp4`, sha256: video.sha256, bytes: video.bytes, durationSeconds: video.durationSeconds,
        width: video.width, height: video.height, fps: video.fps, videoCodec: video.videoCodec, audioCodec: video.audioCodec},
      cover: {file: `covers/${id}.jpg`, sha256: cover.sha256, bytes: cover.bytes},
      publication: {deepLink: `/${q.game}`, utmCampaign: R.CAMPAIGN, ...pub,
        credits: ['scalar', 'tectonic'].includes(q.game) ? ['Map data: Natural Earth'] : [], answerReply: null},
      eligibility: {status: 'qa-passed', notBefore: null, reviewBy: q.reviewBy, expiresAt: null},
    });
  }
  return {generator: {assetKitVersion: 'kit-1'}, fields: {sourceSnapshotHash: doc.snapshotHash, styleRecipes: [...styleRecipes.values()]}, episodes};
}
