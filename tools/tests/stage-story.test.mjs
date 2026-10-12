// node --test tools/tests/*.test.mjs — staging story renders into an Originals batch (tools/stage-story.mjs).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, symlinkSync} from 'node:fs';
import {resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {stage, usedNumbers} from '../stage-story.mjs';

const sha = buf => createHash('sha256').update(buf).digest('hex');

function render(dir, {title = 'The Film', license = 'Pexels', video = 'final video bytes'} = {}) {
  mkdirSync(dir, {recursive: true});
  const mp4 = Buffer.from(video), jpg = Buffer.from(`cover of ${video}`);
  writeFileSync(resolve(dir, 'The_Film.mp4'), mp4);
  writeFileSync(resolve(dir, 'cover.jpg'), jpg);
  writeFileSync(resolve(dir, 'script.json'), '{"title": "x"}\n');
  writeFileSync(resolve(dir, 'render.json'), JSON.stringify({
    renderJsonVersion: 1, engine: 'story', route: 'recap', kitVersion: 'story-1', project: 'originals',
    episodeId: 'originals-recap-the-film-1999', createdAt: '2026-10-12T00:00:00Z',
    job: {input: title, title, year: '1999', format: 'movie-recap', script: 'script.json'},
    video: {file: 'The_Film.mp4', sha256: sha(mp4), bytes: mp4.length, durationSeconds: 58, width: 1080, height: 1920, fps: '30/1', videoCodec: 'h264', audioCodec: 'aac'},
    cover: {file: 'cover.jpg', sha256: sha(jpg), bytes: jpg.length},
    models: [{role: 'llm', id: 'gemini-2.5-flash'}], costUsd: 0.02, costEstimated: true,
    credits: [{kind: 'footage', title: 'Pexels clip', creator: 'A', sourceUrl: 'https://www.pexels.com/video/1/', license, attribution: null, sha256: null}],
    disclosure: {aiGenerated: true, aiKinds: ['script'], realisticSynthetic: false, note: 'Script is AI-generated.'},
  }));
  return dir;
}

function library() {
  const root = mkdtempSync(resolve(tmpdir(), 'stage-'));
  const lib = resolve(root, 'library');
  // An earlier batch already used 001 and 002; a scratch batch used 901
  mkdirSync(resolve(lib, '2026-11-o01'), {recursive: true});
  writeFileSync(resolve(lib, '2026-11-o01/batch.json'), JSON.stringify({episodes: [{episodeId: 'originals-movie-recap-001'}]}));
  mkdirSync(resolve(lib, '2026-11-o01/review/jobs/originals-movie-recap-002'), {recursive: true});
  mkdirSync(resolve(lib, '_dev/2026-10-o901/review/jobs/originals-movie-recap-901'), {recursive: true});
  return {root, lib};
}

test('numbers already used anywhere in the library are skipped', () => {
  const {lib} = library();
  assert.deepEqual([...usedNumbers(lib, 'movie-recap')].sort((a, b) => a - b), [1, 2, 901]);
  assert.deepEqual([...usedNumbers(lib, 'animated-short')], []);
});

test('stages a recap with the next free contract id and a review skeleton', () => {
  const {root, lib} = library();
  const batchDir = resolve(lib, '2026-11-o02');
  const out = stage({batchId: '2026-11-o02', batchDir, folders: [render(resolve(root, 'r1'))], library: lib});
  assert.deepEqual(out, [{episodeId: 'originals-movie-recap-003', workId: 'originals-recap-the-film-1999', staged: true}]);
  const job = resolve(batchDir, 'review/jobs/originals-movie-recap-003');
  const doc = JSON.parse(readFileSync(resolve(job, 'render.json'), 'utf8'));
  assert.equal(doc.episodeId, 'originals-movie-recap-003');
  assert.equal(doc.video.file, 'render.mp4');
  assert.equal(doc.job.workId, 'originals-recap-the-film-1999');
  for (const f of ['render.mp4', 'cover.jpg', 'script.json']) assert.ok(existsSync(resolve(job, f)), f);
  assert.ok(existsSync(resolve(batchDir, 'videos/originals-movie-recap-003.mp4')));
  assert.ok(existsSync(resolve(batchDir, 'covers/originals-movie-recap-003.jpg')));
  const review = JSON.parse(readFileSync(resolve(batchDir, 'review/originals.json'), 'utf8'));
  assert.deepEqual(review.episodes['originals-movie-recap-003'].checks, {rights: false, garbage: false, visualQa: false});
  // Staging the same render again changes nothing; a second render gets the next number
  assert.equal(stage({batchId: '2026-11-o02', batchDir, folders: [resolve(root, 'r1')], library: lib})[0].staged, false);
  const second = stage({batchId: '2026-11-o02', batchDir, folders: [render(resolve(root, 'r2'), {video: 'another'})], library: lib});
  assert.equal(second[0].episodeId, 'originals-movie-recap-004');
});

test('--number starts a scratch range', () => {
  const {root, lib} = library();
  const out = stage({batchId: '2026-10-o902', batchDir: resolve(lib, '_dev/2026-10-o902'), folders: [render(resolve(root, 'r'))], number: 901, library: lib});
  assert.equal(out[0].episodeId, 'originals-movie-recap-902');  // 901 is taken
});

test('refuses unknown licences, finalized batches and misnamed folders', () => {
  const {root, lib} = library();
  assert.throws(() => stage({batchId: '2026-11-o03', batchDir: resolve(lib, '2026-11-o03'), folders: [render(resolve(root, 'u'), {license: 'unknown'})], library: lib}),
    /unknown licence/);
  const done = resolve(lib, '2026-11-o04');
  mkdirSync(done, {recursive: true});
  writeFileSync(resolve(done, 'READY_FOR_UPLOAD'), '');
  assert.throws(() => stage({batchId: '2026-11-o04', batchDir: done, folders: [render(resolve(root, 'f'))], library: lib}), /finalized/);
  assert.throws(() => stage({batchId: '2026-11-o05', batchDir: resolve(lib, 'elsewhere'), folders: [], library: lib}), /must be named/);
  for (const number of ['abc', '-1', '0', '10000'])
    assert.throws(() => stage({batchId: '2026-11-o06', batchDir: resolve(lib, '2026-11-o06'), folders: [render(resolve(root, `n${number}`))], number, library: lib}), /--number/);
});

test('render files must stay inside the render folder', () => {
  const {root, lib} = library();
  const dir = render(resolve(root, 'esc'));
  const doc = JSON.parse(readFileSync(resolve(dir, 'render.json'), 'utf8'));
  writeFileSync(resolve(root, 'secret.txt'), 'not a script');
  writeFileSync(resolve(dir, 'render.json'), JSON.stringify({...doc, job: {...doc.job, script: '../secret.txt'}}));
  assert.throws(() => stage({batchId: '2026-11-o07', batchDir: resolve(lib, '2026-11-o07'), folders: [dir], library: lib}), /job.script/);
  symlinkSync(resolve(root, 'secret.txt'), resolve(dir, 'link.json'));
  writeFileSync(resolve(dir, 'render.json'), JSON.stringify({...doc, job: {...doc.job, script: 'link.json'}}));
  assert.throws(() => stage({batchId: '2026-11-o08', batchDir: resolve(lib, '2026-11-o08'), folders: [dir], library: lib}), /outside the render folder/);
});
