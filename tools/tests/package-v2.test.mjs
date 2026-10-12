// node --test tools/tests/*.test.mjs — contract v2 packaging: the Originals core and the shared core's v2 pieces,
// checked against the Python validator (document checks; contract/library_contract.py).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {TMDB_NOTICE} from '../render-json-core.mjs';
import {batchDocument, renderErrors, requiredAttributions} from '../package-core.mjs';
import {originalsEpisodes} from '../../projects/originals/package-core.mjs';

const ROOT = resolve(import.meta.dirname, '../..');
const json = p => JSON.parse(readFileSync(resolve(ROOT, p), 'utf8'));
const studio = json('studio.json'), project = json('projects/originals/project.json');
const TMDB_ATTR = `Data and images from TMDB (themoviedb.org). ${TMDB_NOTICE}.`;
const WIKI_ATTR = 'Plot adapted from the Wikipedia article "The Film" by Wikipedia contributors, licensed under CC BY-SA 4.0.';

const credit = (kind, title, license, attribution = null, sourceUrl = 'https://example.org/a') =>
  ({kind, title, creator: null, sourceUrl, license, attribution, sha256: null});

function recap(id = 'originals-recap-001') {
  return {
    renderJsonVersion: 1, engine: 'story', route: 'recap', kitVersion: 'story-1', project: 'originals', episodeId: id,
    createdAt: '2026-10-12T00:00:00Z',
    job: {input: 'The Film', title: 'The Film', year: '1999', format: 'movie-recap', plotSource: 'Wikipedia', plotUrl: 'https://en.wikipedia.org/wiki/The_Film', tmdbId: 603},
    video: {file: 'final.mp4', sha256: 'a'.repeat(64), bytes: 10, durationSeconds: 58.2, width: 1080, height: 1920, fps: '30/1', videoCodec: 'h264', audioCodec: 'aac'},
    cover: {file: 'cover.jpg', sha256: 'b'.repeat(64), bytes: 5},
    models: [{role: 'llm', id: 'gemini-2.5-flash'}, {role: 'tts', id: 'gemini-tts'}, {role: 'asr', id: 'whisper-base'}], costUsd: 0.02, costEstimated: true,
    credits: [credit('text', 'Narration script', 'generated', null, null), credit('voice', 'Narration voice', 'generated', null, null),
      credit('text', 'Plot of The Film (Wikipedia)', 'Wikipedia-CC-BY-SA', WIKI_ATTR), credit('data', 'Release year (TMDB)', 'TMDB', TMDB_ATTR),
      credit('poster', 'The Film poster', 'TMDB', TMDB_ATTR), credit('footage', 'Pexels video', 'Pexels', 'Video by A on Pexels'),
      credit('music', 'Calm bed', 'CC0-1.0')],
    disclosure: {aiGenerated: true, aiKinds: ['script', 'voice'], realisticSynthetic: false, note: 'Script and narration are AI-generated.'},
  };
}

const review = {reviewer: 'owner', episodes: {'originals-recap-001': {checks: {rights: true, garbage: true, visualQa: true}}}};
const hashes = {'originals-recap-001': 'c'.repeat(64)};

function validate(body) {
  const code = 'import sys, json, datetime as dt; sys.path.insert(0, "contract"); import library_contract as lc; '
    + 'r = lc.validate_document(json.load(sys.stdin), now=dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc)); print(json.dumps(r.errors))';
  const out = spawnSync('python3', ['-c', code], {cwd: ROOT, input: body, encoding: 'utf8'});
  assert.equal(out.status, 0, out.stderr);
  return JSON.parse(out.stdout);
}

test('an Originals recap packages into a valid v2 batch with every attribution', () => {
  const p = originalsEpisodes({renders: [recap()], project, studio, review, renderHashes: hashes});
  const body = batchDocument({project, batchId: '2026-10-o01', createdAt: '2026-10-12T01:00:00Z', commit: 'd'.repeat(40), dirty: false, packaged: p});
  assert.deepEqual(validate(body), []);
  const doc = JSON.parse(body);
  assert.deepEqual(Object.keys(doc), ['schemaVersion', 'batchId', 'createdAt', 'project', 'generator', 'styleRecipes', 'projectData', 'episodes']);
  const e = doc.episodes[0];
  assert.equal(e.contentId, 'originals:movie-recap:the-film-1999');
  assert.deepEqual(e.render, {engine: 'story', route: 'recap', renderer: null, kitVersion: 'story-1', renderSha256: 'c'.repeat(64),
    models: recap().models, costUsd: 0.02});
  assert.ok(e.publication.captions.instagram.includes(TMDB_ATTR) && e.publication.captions.instagram.includes(WIKI_ATTR));
  // X and Bluesky cannot hold both attributions: they get no caption (they do not post), with a warning.
  assert.equal(e.publication.captions.x, null);
  assert.ok(p.warnings.some(w => w.includes('no x caption')));
});

test('a failed review check or a missing review entry stops packaging', () => {
  const bad = {reviewer: 'owner', episodes: {'originals-recap-001': {checks: {rights: true, garbage: false, visualQa: true}}}};
  assert.throws(() => originalsEpisodes({renders: [recap()], project, studio, review: bad, renderHashes: hashes}), /garbage/);
  assert.throws(() => originalsEpisodes({renders: [recap('originals-recap-002')], project, studio, review, renderHashes: hashes}), /no entry/);
});

test('contract v2 refuses unknown licences in render.json; v1 still reads them', () => {
  const render = recap();
  render.credits.push(credit('music', 'Untracked bed', 'unknown'));
  const opts = {folder: 'originals-recap-001', project, known: new Set(['originals'])};
  assert.match(renderErrors(render, opts).join(';'), /unknown licence/);
  assert.deepEqual(renderErrors(render, {...opts, schemaVersion: 1}), []);
});

test('required attributions: each attribution once, the TMDB notice folded into a TMDB attribution', () => {
  assert.deepEqual(requiredAttributions(recap().credits), [WIKI_ATTR, TMDB_ATTR]);
  assert.deepEqual(requiredAttributions([credit('poster', 'P', 'TMDB', TMDB_NOTICE)]), [TMDB_NOTICE]);
  assert.deepEqual(requiredAttributions([credit('music', 'M', 'CC0-1.0')]), []);
});
