# Library video generation (Mac)

Generates the self-contained 1080×1920 quiz videos and their `batch.json` for the Pi publisher. Creative plan and decisions: scalargame `docs/growth/VIDEO_GENERATION_PIPELINE.md`. Output contract: `contract/BATCH_CONTRACT.md`, validated by `contract/library_contract.py` (owned by the publishing build: never edit it here). No uploads, no Pi access, no publishing from this pipeline.

## Pipeline

Run every command from the repo root. The game repo is found by `lib.mjs` `GAME_DIR`: `$SCALARGAME_DIR`, else the parent folder (repo at `scalargame/marketing`), else the sibling `../scalargame`.

```bash
# 1. Freeze canonical game sources (committed scalargame HEAD only); refuses an existing snapshot ID
node studio/pipeline/snapshot.mjs --id=2026-10-06-3921b9e
# 2. Generate many checked candidates (ideas), then curate questions-<set>.mjs (QUESTIONS + CONFIG) by hand.
#    Refuses to replace a different candidates.json in a snapshot folder: for a reused snapshot use --out
node studio/pipeline/candidates.mjs --snapshot=2026-10-06-3921b9e --today=2026-10-06 [--out=<file.json>]
# 3. Re-check the curated set deterministically → <CONFIG.outDir ?? library/_sources/<snapshot>>/questions-<set>.json
node studio/pipeline/check.mjs [--questions=questions-<set>.mjs]          # default: questions-2026-10 (regression set)
# 4. Question pack for owner review (Checkpoint 1) → <batch dir>/review/question-pack.html
node studio/pipeline/pack.mjs --set=questions-<set> [--batch=<id>] [--out=<file>]
# 5. Music beds (once per corpus change; sources in studio/music/sources/, Mac only) → studio/public/episodes/music/*.m4a + beds.json
studio/.venv/bin/python studio/pipeline/music_catalog.py      # measure + pick 15 calm tracks per game → studio/music/catalog.json
studio/.venv/bin/python studio/pipeline/music_beds.py --picks # calm beds <game>-<duration>-<trackId> (no args: the retired 2026-10 Gemini beds)
# 6. Freeze immutable per-episode render inputs → library/<batch>/review/jobs/<episodeId>/{input,props}.json
node studio/pipeline/episodes.mjs --batch=<batchId> --set=questions-<set>
# 7. Render: resumable per-episode jobs via studio/render/render.sh LibraryEpisode; QA; copy to videos/ + covers/ only when validated
node studio/pipeline/render.mjs --batch=<batchId>            # re-run to resume; --only=id1,id2; --rerender
# 8. batch.json (captions etc. from deterministic templates); --dry first
node studio/pipeline/batch.mjs --batch=<batchId> --set=questions-<set>
# 9. Contract validation, review sheet (Checkpoint review), then finalize only after owner approval
python3 contract/library_contract.py validate library/<batchId>
node studio/pipeline/review.mjs --batch=<batchId>           # → library/<batchId>/review/index.html
python3 contract/library_contract.py finalize library/<batchId>   # writes READY_FOR_UPLOAD; files immutable after
```

Every stage that writes into a batch folder (`pack`, `episodes`, `render`, `batch`, `review`) refuses a folder with `READY_FOR_UPLOAD`. `--set` (and `--questions` for `check`/`pack`) takes a name in `studio/pipeline/` or a repo-relative path to a set module anywhere (rehearsals keep theirs in `library/_dev/`). `--dir=<folder>` writes a batch somewhere other than `library/<batchId>/` (the folder name must still equal the batch ID for the validator).

Dev helpers: `episodes.mjs --fixtures` writes props for every question to `library/_dev/fixtures/`; render a still from `studio/` with `./node_modules/.bin/remotion still src/index.ts LibraryEpisode out.png --props=<props.json> --frame=<n>` (add `"showSafeArea": true` to a props copy for the safe-area overlay); `batch.mjs --dry` checks captions for every main question against the contract early (always writes `library/_dev/batch-dry.json`); test chains run in a scratch batch with `--dir=library/_dev/<batch>`.

## Per-batch config

Each question set module (`questions-<set>.mjs`) exports `SNAPSHOT`, `TODAY`, `WHENABOUTS_FRESHNESS`, `QUESTIONS` and `CONFIG`. Nothing batch-specific lives in the stage scripts; they read it from `CONFIG` (loaded by `lib.mjs` `loadSet`). `questions-2026-10.mjs` holds the values the 2026-10 batches were made with and is the default set, so `node studio/pipeline/check.mjs` still reproduces `questionsHash` `5ab19d44…` and `git diff --exit-code library/_sources` stays clean.

| `CONFIG` key | Used by | Meaning |
|---|---|---|
| `batches` | check, episodes, batch, pack | Batch IDs this set feeds (2026-10: pilots + b01). `episodes`/`batch` refuse a batch not listed (`--select`/`--dry` aside). |
| `scope` | check, pack | Main (non-spare) questions per `'game/format'`; any game/format not listed must have none. |
| `mix` | check | `[approachable, moderate, challenging]` per `'game'` or per `'game/format'`. |
| `pilotsPerGame` | check | Pilots per game in scope (0 = no pilots). |
| `styles`, `beds` | episodes, batch `--dry` | Style recipe per game. `beds`: `'calm'` (default for new sets: the game's calm beds of matching length, rotated least-recently-used by track across the library; a frozen episode keeps its bed), or per format a bed name, a list, or `'calm'`. Beds must exist in `public/episodes/music/beds.json` and match `timing.ts`. |
| `episodes` | check, episodes | Permanent `key → [batchId, '<game>-<short>-<nnn>']` for every main question. `check.mjs` refuses a missing ID (and prints the next free one, numbered after every `library/<batch>/batch.json` and frozen job input), an ID or `questionId` used by a different episode anywhere in `library/<batch>/`, a spare with an ID, and a wrong prefix. Short formats: `clues`, `elimination`, `headtohead`, `slot`, `year`, `beforeafter`, `missing`, `neighbors`. |
| `experimentId`, `variantId` | batch | Written to every episode. |
| `reviewer` | batch | `evidence.reviewer` text (who approved the pack, and the Checkpoint 1 date). |
| `verification` | batch, pack | Fact-check file; default `<batch dir>/review/source-verification.json`. `batch.mjs` refuses an episode with no result, or a `concern`/`fail` without a written `resolution`. |
| `outDir` | check, pack, episodes, batch | Where `questions-<set>.json` is written and read; default `library/_sources/<SNAPSHOT>`. Rehearsals point it into `library/_dev/`. |
| `candidates` | pack | Candidates file for the pack's counts; default `<outDir>/candidates.json`. Set it when a reused snapshot's candidates were regenerated with `--out` for a new `--today`. |
| `pack` | pack | Optional prose overrides: `title`, `intro(ctx)`, `snapshotNote`, `checksNote`, `sourceCheckNote`, `notes(ctx)`. 2026-10's historical pack prose is `pack-2026-10.mjs`. |

Constants that stay in code on purpose: the legacy ep01–ep08 repeat list in `check.mjs` (published before this pipeline, applies to every batch), D13 lists, display names and data-defect notes in `lib.mjs` (editorial policy, not per batch), kit version `kit-1`, music/SFX volumes, UTM campaign and hashtags in `batch.mjs` (contract-level). Reference retrieval dates and the Factbook mirror commit are read from the snapshot's `data/reference/README.md`.

## What each stage guarantees

| Stage | Guarantees |
|---|---|
| `check.mjs` | Unique answer (Scalar/Tectonic within the 195/194-country universe), each elimination clue removes a candidate, numeric clues ambiguous within ±3% count both ways, game data and pinned World Bank/Factbook references agree, Continuum order holds in game data and World Bank (adjacent ratio ≥ 1.15 population, ≥ 1.10 area, one reference year), Whenabouts reviewed-fact fingerprints match the event, Tectonic land neighbors agree in Factbook and globe adjacency, decoys are outside the Tectonic map window, no repeat of published legacy ep01–ep08, D13 sensitive/contested exclusions, no Scalar answer that is a Countries Daily pick in the next 90 days, answer absent from pre-reveal text, every explanation number/list filled from data (hand claims need `asserts`), the configured difficulty mix and per-format counts, and answer letters vary within each format of two or more episodes. No `questionId` or episode ID reused from any `library/<batch>/`; batch rules (scope, mix, pilots) from `CONFIG`. Mutation-tested. |
| `episodes.mjs` | Inputs are frozen; a changed input after rendering is refused (new revision needed). `--replace-unrendered` only replaces inputs that were never rendered. |
| `render.mjs` | One job per episode, every attempt logged in `status.json`; failed/partial work stays in the job folder. Validated only if: H.264 yuv420p 1080×1920 30/1, AAC 48 kHz stereo, fast-start, duration exact, ≤ 24,000,000 bytes, −14 ± 2 LUFS, true peak ≤ −1 dBTP, no black segments, no silence gaps, cover ≤ 2 MB. Refuses to run on a finalized batch. |
| `render.sh LibraryEpisode` | PNG frames (true yuv420p), WAV mix mastered to −14 LUFS / ≤ −1 dBTP (`master_audio.py`), fdk-AAC mux with edit list, `check_sync.py` (0 ms). Lives in `studio/render/`. |
| `batch.mjs` | Every episode has a fact-check result (concerns resolved); contract v1 fields only; the answer appears in text only as one item of the full choice list; poll questions never contain it; `{link}` only on Facebook/Threads/X/Bluesky; per-platform length limits; `answerReply` null. |

## Layout

- `studio/src/episodes/` Remotion kit-1: `LibraryEpisode.tsx` (composition, audio cue sheet), `timing.ts` (per-format timings; asserts ≥ 6 s thinking), `kit/` (ui, motion, geo), `styles/<styleId>.ts` (one recipe per game per batch), `templates/<game>/` (eight formats), `fonts.ts` (OFL fonts in `studio/public/episodes/fonts`). `studio/src/fonts.ts` (imported by `Root.tsx`) also registers Fraunces 700, which the Whenabouts style uses: keep it.
- `studio/public/episodes/music/` cut beds + `beds.json` (source/output hashes, segments, loudness, rights).
- `library/_sources/<snapshot>/` frozen sources, `candidates.json`, `questions-<set>.json`. `library/<batch>/` per contract; only `library/*/batch.json` is tracked in git.
