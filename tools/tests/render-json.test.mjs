// node --test tools/tests/*.test.mjs
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {checkRender, TMDB_NOTICE} from '../render-json.mjs';

const base = () => ({
  renderJsonVersion: 1, engine: 'story', route: 'recap', kitVersion: 'story-1', project: 'originals', episodeId: 'originals-recap-x',
  createdAt: '2026-10-12T00:00:00Z', job: {},
  video: {file: 'final.mp4', sha256: 'a'.repeat(64), bytes: 10, durationSeconds: 30.5, width: 1080, height: 1920, fps: '30/1', videoCodec: 'h264', audioCodec: 'aac'},
  cover: {file: 'cover.jpg', sha256: 'b'.repeat(64), bytes: 5},
  models: [{role: 'llm', id: 'gemini-2.5-flash'}, {role: 'tts', id: 'gemini-tts'}], costUsd: 0.02, costEstimated: true,
  credits: [{kind: 'poster', title: 'Poster', creator: null, sourceUrl: 'https://image.tmdb.org/t/p/original/x.jpg', license: 'TMDB', attribution: TMDB_NOTICE, sha256: null}],
  disclosure: {aiGenerated: true, aiKinds: ['script', 'voice'], realisticSynthetic: false, note: 'Script and narration are AI-generated.'},
});

test('a complete story recap render.json is valid', () => {
  assert.deepEqual(checkRender(base(), {projects: new Set(['originals'])}), []);
});

test('paths, licences, attribution and disclosure are enforced', () => {
  const cases = [
    [d => { d.video.file = '../x.mp4'; }, /video.file/],
    [d => { d.credits[0].attribution = 'TMDB'; }, /TMDB notice/],
    [d => { d.credits[0].license = 'CC-BY-4.0'; d.credits[0].attribution = null; }, /needs attribution/],
    [d => { d.credits[0].license = 'mystery'; }, /license/],
    [d => { d.disclosure = {aiGenerated: false, aiKinds: [], realisticSynthetic: false, note: 'n'}; }, /generative model/],
    [d => { d.disclosure.aiKinds = []; }, /exactly when/],
    [d => { d.route = null; }, /route/],
    [d => { d.costUsd = -1; }, /costUsd/],
    [d => { d.project = 'other'; }, /unknown project/],
  ];
  for (const [mutate, pattern] of cases) {
    const doc = base(); mutate(doc);
    assert.match(checkRender(doc, {projects: new Set(['originals'])}).join('\n'), pattern);
  }
});
