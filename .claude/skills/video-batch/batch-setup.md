# Per-batch pipeline setup

The stage scripts hold no batch-specific values. Everything a batch needs lives in its question set module, `engines/motion/pipeline/questions-<set>.mjs` (one set per batch, e.g. `questions-2026-11-b02`): `SNAPSHOT`, `TODAY`, `WHENABOUTS_FRESHNESS`, `QUESTIONS` and a `CONFIG` export. Full key reference: `engines/motion/pipeline/README.md` → "Per-batch config". Copy the shape of `questions-2026-10.mjs` (minus its `pack` prose) or of the rehearsal set `library/_dev/dryrun2-work/questions-2026-10-dryrun2.mjs`.

```js
export const SNAPSHOT = '<snapshotId>';
export const TODAY = 'YYYY-MM-DD';
export const WHENABOUTS_FRESHNESS = 'strict';          // 'waived' only if the brief says so, with the reason in a comment
export const CONFIG = {
  batches: ['<batchId>'],                               // add the pilots batch first if the brief asks for pilots
  scope: {'scalar/progressive-clues': 3, /* … one entry per brief Scope row */},
  mix: {scalar: [3, 2, 1] /* or per format: 'scalar/progressive-clues': [1, 1, 1] */},
  pilotsPerGame: 0,                                     // 1 when the brief asks for pilots
  styles: {scalar: 'scalar-notebook-1', continuum: 'continuum-poster-1', whenabouts: 'whenabouts-almanac-1', tectonic: 'tectonic-ocean-1'},
  beds: 'calm',                                         // rotating calm pool per game (docs/AUDIO_CORPUS_PLAN.md); or per format: name | [names] | 'calm'
  episodes: {},                                         // filled from check.mjs's "next free" lines (below)
  experimentId: '<from the brief>', variantId: null,
  reviewer: 'owner (question pack approved at Checkpoint 1, YYYY-MM-DD); independent web source check',
  // verification defaults to library/<batchId>/review/source-verification.json
  // outDir defaults to library/_sources/<SNAPSHOT>; candidates to <outDir>/candidates.json (see "Reused snapshot")
};
export const QUESTIONS = [ /* curated from candidates */ ];
```

`beds: 'calm'` gives each new episode the least recently used track (library-wide) among its game's calm beds of the right length, so music rotates across episodes and batches; a frozen episode keeps its bed. The 2026-10 Gemini beds (`scalar-24`, `continuum-20`, …) are retired: use them only if the brief asks. Only `styles`/`beds` that exist (`engines/motion/src/projects/scalargame/styles/<id>.ts`, `engines/motion/public/episodes/music/beds.json`) work; new ones are template/music work with a pilot. New formats need a contract change first (`contract/BATCH_CONTRACT.md`, owner approval, validator and tests). Template work follows `library/_dev/TEMPLATE_BRIEF.md` (its paths predate the move: `src/library` is now `engines/motion/src/episodes`).

## Episode IDs

Leave `episodes: {}` and run `check.mjs`: for every main question it fails with `no episode ID … (next free: '<key>': ['<batchId>', '<game>-<short>-<nnn>'])`. Paste those lines into `CONFIG.episodes` (use the right batch when there are pilots). Numbers continue after every ID in `library/<batch>/batch.json` and frozen job inputs (`library/<batch>/review/jobs/*/input.json`); scratch folders (`library/_*`) don't count. Once an ID is in `CONFIG.episodes` it is permanent: never renumber or reuse it. `check.mjs` also refuses any `questionId` or episode ID already used by a different episode in the library, and prints a `note:` when a subject (country, event) reappears in a different question.

```bash
# questionIds and episodeIds already used (never repeat a questionId; never reuse an episodeId)
python3 -c "import json,glob; e=[x for f in sorted(glob.glob('library/*/batch.json')) for x in json.load(open(f))['episodes']]; print('\n'.join(sorted(f\"{x['episodeId']}  {x['questionId']}\" for x in e)))"
```

## Reused snapshot

`candidates.mjs` refuses to replace a snapshot's existing `candidates.json` with different content (it is tracked evidence). When the brief reuses a snapshot with a new `--today`, write the candidates next to it under a new name and point the set at it:

```bash
node engines/motion/pipeline/candidates.mjs --snapshot=<id> --today=<date> --out=library/_sources/<id>/candidates-<set>.json
# CONFIG.candidates = 'library/_sources/<id>/candidates-<set>.json'
```

Adding new files (`candidates-<set>.json`, `questions-<set>.json`) to a snapshot folder is fine; changing an existing one is not.

## Regression check (run after any pipeline change)

```bash
node engines/motion/pipeline/check.mjs                       # default set questions-2026-10 → questionsHash 5ab19d441ad8a8e2…
git status --porcelain library/_sources              # must print nothing
(cd engines/motion && ./node_modules/.bin/tsc --noEmit)
```

Show Samir any pipeline diff at Checkpoint 0 or 1. Code changes need his OK and are committed only when he asks.

## Rehearsal (scratch batch)

A rehearsal never touches `library/_sources/` or `library/_briefs/`: brief in `library/_dev/briefs/<id>.md`, set module in `library/_dev/<work>/questions-<id>.mjs` with `CONFIG.outDir: 'library/_dev/<work>'` and `CONFIG.verification: 'library/_dev/<id>/review/source-verification.json'`, candidates with `--out=library/_dev/<work>/candidates.json`, and `--set=library/_dev/<work>/questions-<id>.mjs --dir=library/_dev/<id>` on `pack`, `episodes`, `render`, `batch` and `review` (`check` takes `--questions=<same path>`). Validate with `python3 contract/library_contract.py validate library/_dev/<id>`; retro draft in `library/_dev/retros/`. Never finalize a rehearsal. Worked example: 2026-10-dryrun2 (`library/_dev/retros/2026-10-dryrun2.md`).
