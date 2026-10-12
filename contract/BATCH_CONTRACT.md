# Video batch contract (Mac generation → Pi publishing)

Status: v1 specification, agreed 6 October 2026; v2 (one project per batch) approved 11 October 2026 (`docs/STUDIO_PLAN.md` §5, CHECKPOINT 1), `render.renderer` added 12 October 2026. v1 stays valid forever: the validator dispatches on `schemaVersion`. This is the only interface between the video generation pipeline (scalargame repo: `docs/growth/VIDEO_GENERATION_PIPELINE.md`; this repo: [engines/motion/pipeline](../studio/pipeline/README.md)) and the publishing pipeline ([PUBLISHING_PIPELINE_PLAN.md](../publisher/docs/PUBLISHING_PIPELINE_PLAN.md)). Either side can change internally. Changing this file needs owner approval, a `schemaVersion` bump if the change is incompatible, and an update to the validator and its tests.

Validator (owned by the publishing build, stdlib Python, runs on Mac and Pi):

```bash
python3 contract/library_contract.py validate library/<batchId>   # Mac: before upload
python3 contract/library_contract.py finalize library/<batchId>   # Mac: validate, then write READY_FOR_UPLOAD
```

The Pi importer calls the same module. A batch the Mac validator accepts is one the Pi accepts.

## Standard location

```
marketing/library/
  <batchId>/
    batch.json                 # the one metadata file for every video in the batch
    videos/<episodeId>.mp4     # final delivery files (the only videos uploaded)
    covers/<episodeId>.jpg     # spoiler-free covers
    review/                    # never uploaded: storyboards, contact sheets, source evidence, masters
    READY_FOR_UPLOAD           # written only by `finalize` after validation passes
```

- `batchId`: `YYYY-MM-<slug>`, lowercase `[a-z0-9-]`, e.g. `2026-10-pilots`, `2026-10-b01`. Pi-created single uploads use `manual-YYYYMMDD-<n>`.
- `episodeId`: `<game>-<format>-<nnn>`, e.g. `scalar-clues-001`. Unique forever; never reused for different content.
- Git: `library/` is gitignored except `library/*/batch.json`. Masters and media stay local (D20). Back up the whole folder separately.
- Files are immutable once `READY_FOR_UPLOAD` exists. Corrections create a new revision (below); never edit an uploaded file in place.

## Upload workflow

1. On the Mac: `finalize` passes → `READY_FOR_UPLOAD`.
2. In the Pi UI (Mac browser): Library → Add batch → choose `batch.json`. The UI lists the files it expects.
3. Select the `videos/` and `covers/` files (multi-select). Each file uploads in its own request, is hashed while streaming, and is matched to `batch.json` by sha256. Interrupted files show as missing and can be re-selected. Files already on the Pi (same hash) are skipped.
4. An episode becomes reviewable when its video and cover are verified. Owner content approval in the Pi UI is the approval of record.

### Adding to an existing library ("merge, never overwrite")

| Situation | Pi behaviour |
|---|---|
| New `batchId` | New batch added |
| Same `batchId`, same episode, same hashes | No-op ("already imported") |
| Same episode, higher `revision`, new hash | New revision, needs approval; earlier revision and its approvals/receipts untouched |
| Same episode, same or lower `revision`, different hash | Rejected: bump the revision |
| `questionId` already posted on an account (ledger, including legacy `ep01`–`ep08`) | Imported. Excluded from that account in schedules, with the reason shown |
| A schedule is already approved | Never changed. New videos are available for the next draft |

Existing Pi media (the 2026-10-05 batch in `/var/lib/scalar-social/catalog.json` and `site/`) is registered as batch `legacy-2026-10-05` in place, with `questionId` equal to its old `ep` ID, so existing duplicate protection carries over.

## `batch.json` (schemaVersion 1)

```json
{
  "schemaVersion": 1,
  "batchId": "2026-10-pilots",
  "createdAt": "2026-10-08T14:00:00Z",
  "generator": { "repoCommit": "<sha>", "dirty": false, "assetKitVersion": "kit-1" },
  "sourceSnapshotHash": "<sha256 of frozen game data/sources>",
  "styleRecipes": [ { "styleId": "scalar-paper-1", "game": "scalar", "version": 1, "summary": "…" } ],
  "episodes": [
    {
      "episodeId": "scalar-clues-001",
      "questionId": "scalar:BOL:clues",
      "revision": 1,
      "game": "scalar",
      "format": "progressive-clues",
      "language": "en",
      "difficulty": "approachable",
      "styleId": "scalar-paper-1",
      "experimentId": "baseline-2026-10",
      "variantId": null,
      "creative": {
        "hook": "Three clues. One country.",
        "question": "Which country?",
        "clues": ["Americas", "Landlocked", "5 neighbours"],
        "choices": [ { "key": "A", "label": "Bolivia" }, { "key": "B", "label": "Paraguay" }, { "key": "C", "label": "Austria" } ],
        "answer": "Bolivia",
        "answerAliases": ["BOL", "Plurinational State of Bolivia"],
        "explanation": "…"
      },
      "evidence": {
        "sources": [ { "title": "…", "url": "https://…", "retrieved": "2026-10-07" } ],
        "checks": { "uniqueAnswer": true, "candidateCounts": [41, 2, 1] },
        "reviewer": "owner"
      },
      "music": { "trackId": "…", "sha256": "…", "license": "owner-supplied" },
      "video": { "file": "videos/scalar-clues-001.mp4", "sha256": "…", "bytes": 9123456,
                 "durationSeconds": 22.0, "width": 1080, "height": 1920, "fps": "30/1",
                 "videoCodec": "h264", "audioCodec": "aac" },
      "cover": { "file": "covers/scalar-clues-001.jpg", "sha256": "…", "bytes": 120345 },
      "publication": {
        "deepLink": "/scalar",
        "utmCampaign": "social_library_v1",
        "captions": {
          "instagram": "Three clues, one country. A) Bolivia B) Paraguay C) Austria — comment your letter. Play a new puzzle at scalargame.com",
          "facebook": "… {link}",
          "threads": "… {link}",
          "x": "… {link}",
          "bluesky": "… {link}",
          "tiktok": "…"
        },
        "youtube": { "title": "Which country? Three clues #shorts", "description": "…" },
        "altText": "Animated quiz: three clues about a mystery country, answer revealed at the end.",
        "hashtags": ["#geography", "#quiz"],
        "credits": [],
        "poll": { "question": "Which country?", "options": ["Bolivia", "Paraguay", "Austria"] },
        "firstComment": { "instagram": "A) Bolivia  B) Paraguay  C) Austria — comment your letter", "threads": null, "bluesky": null, "x": null },
        "answerReply": null
      },
      "eligibility": { "status": "qa-passed", "notBefore": null, "reviewBy": "2027-04-01", "expiresAt": null }
    }
  ]
}
```

### Field rules

- `questionId` is the duplicate key (D22: once per account, no exact repeats). Style variants of the same question share it and differ in `variantId`.
- `game`: `scalar | continuum | whenabouts | tectonic`. `format`: `progressive-clues | candidate-elimination | head-to-head | missing-slot | guess-the-year | before-after | missing-country | neighbor-clues` (the eight confirmed formats; new formats need a contract update).
- `difficulty`: `approachable | moderate | challenging`.
- `{link}` in a caption is expanded by the Pi to `https://www.scalargame.com<deepLink>?utm_source=<platform>&utm_medium=organic_social&utm_campaign=<utmCampaign>&utm_content=<episodeId>`. Instagram/YouTube/TikTok captions should not rely on clickable links.
- `poll.options`: 2–4 items, each 1–25 characters (Threads limit), containing the answer exactly once. `null` if the episode has no choices.
- `firstComment` / `answerReply`: optional per platform; `null` means none. `answerReply` is `{ "text": "…", "delayHours": n }` and must start with a spacer line; it's the only field allowed to contain the answer.
- `eligibility.status` from the Mac is always `qa-passed`. Only the Pi records `approved`, `withdrawn` or `expired`. Dates are `YYYY-MM-DD` (`notBefore`/`reviewBy`/`expiresAt`); timestamps are UTC ISO-8601 with `Z`.

### Validation (`library_contract.py`, Mac and Pi)

- JSON shape, enums, ID formats, unique `episodeId`s; `file` paths only `videos/<episodeId>.mp4` and `covers/<episodeId>.jpg` (no other paths, no `..`).
- sha256 and byte size of every referenced file; ffprobe re-measurement must match `video` (never trusted from the JSON).
- Media hard rules: H.264 video, `yuv420p`, 9:16, AAC 48 kHz stereo or no audio, ≤ 24,000,000 bytes, fast-start. Per-platform duration/frame-rate limits are applied by the Pi when scheduling.
- Spoiler gate: no caption, YouTube title/description, alt text, poll question, first comment or cover file name contains `answer` or any `answerAliases` (case- and accent-insensitive).
- Per-platform caption length limits; `{link}` only where the platform shows clickable links; choices contain the answer exactly once.
- `reviewBy`/`expiresAt` not in the past at import; `generator.dirty: true` is a warning, shown in the Pi review screen.


## `batch.json` (schemaVersion 2)

One project per batch. The project's rules live in `contract/projects/<project>.py` (synced to the Pi, so the Pi checks everything the Mac checks); the core rules below apply to every project. Media rules, file paths, the upload workflow, merge rules and finalize are unchanged from v1.

```json
{
  "schemaVersion": 2,
  "batchId": "2026-11-o01",
  "createdAt": "2026-11-02T14:00:00Z",
  "project": "originals",
  "generator": { "repoCommit": "<sha>", "dirty": false },
  "styleRecipes": [],
  "projectData": null,
  "episodes": [
    {
      "episodeId": "originals-recap-001",
      "contentId": "originals:movie-recap:the-film-1999",
      "revision": 1,
      "format": "movie-recap",
      "language": "en",
      "render": { "engine": "story", "route": "recap", "renderer": null, "kitVersion": "story-1",
                  "renderSha256": "<sha256 of render.json>", "models": [ { "role": "llm", "id": "…" } ], "costUsd": 0.12 },
      "experimentId": null, "variantId": null, "tags": [],
      "video": { "…": "as v1" }, "cover": { "…": "as v1" },
      "link": null,
      "publication": { "captions": { "…": "…" }, "youtube": { "title": "…", "description": "…" }, "altText": "…",
                       "hashtags": [], "poll": null, "firstComment": null, "answerReply": null },
      "credits": [ { "kind": "poster", "title": "…", "creator": null, "sourceUrl": "https://…", "license": "TMDB",
                     "attribution": "This product uses the TMDB API but is not endorsed or certified by TMDB", "sha256": null } ],
      "disclosure": { "aiGenerated": true, "aiKinds": ["script", "voice"], "realisticSynthetic": false, "note": "…" },
      "eligibility": { "status": "qa-passed", "notBefore": null, "reviewBy": "2027-04-01", "expiresAt": null },
      "projectData": { "…": "validated by contract/projects/originals.py" }
    }
  ]
}
```

### Core rules (every project)

- Batch: `project` is a registered project; `generator` is `{repoCommit, dirty}` (`dirty: true` is a warning); `styleRecipes` items are `{styleId, engine, version, summary}` (may be empty); `projectData` is the project's batch fields (or null).
- `episodeId`: `<prefix>-<format-slug>-<nnn>` (≤ 120 characters), prefixes declared by the project. Unique forever.
- `contentId`: the duplicate key, `<namespace>:<id>` (no spaces or `#`). Namespaces are declared by the project and unique across projects; a namespace of another project is refused. Scalargame's namespaces are its games, and its contentIds equal the v1 questionIds, so v1 and v2 share the Pi's ledger.
- `format`: one of the project's formats; `render.engine`/`render.route` must be the engine and route that make it.
- `render`: `engine` ∈ `motion`, `story`; `route` null for motion, `recap`/`series` for story; `renderer` ∈ `render.sh`, `web` or null (who rendered a motion episode: the Mac's `render.sh` or the Studio's browser export); `kitVersion`; `renderSha256` = sha256 of the engine's `render.json` file; `models` = `[{role, id}]` with role ∈ llm, tts, image, video, music, asr; `costUsd` ≥ 0.
- `tags`: up to 20 unique `[a-z0-9-]` labels for Learn.
- `link`: null or `{url, utmCampaign}` (HTTPS, no query, fragment or credentials; the project may restrict the host and may require a link). `{link}` in a text is allowed only when the link is non-null and only where v1 allows it; it expands to `url?utm_source=<platform>&utm_medium=organic_social&utm_campaign=<utmCampaign>&utm_content=<episodeId>`.
- `publication`: v1 fields minus `deepLink`, `utmCampaign`, `credits`, with the v1 length, placeholder, link-platform and spoiler rules (the project supplies the spoiler terms). The project may forbid `poll` and `answerReply`.
- `credits`: one entry per third-party, owner or generated asset: `{kind, title, creator, sourceUrl, license, attribution, sha256}`; `kind` ∈ footage, image, poster, music, sfx, font, voice, data, text, model; `license` ∈ CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0, OFL-1.1, Pexels, Pixabay, TMDB, Wikipedia-CC-BY-SA, owner, generated, public-domain (`unknown` is refused). CC-BY-4.0, CC-BY-SA-4.0, TMDB and Wikipedia-CC-BY-SA need `attribution` text; TMDB attribution contains the TMDB notice.
- **Attribution rule**: every platform that would post (each non-null caption, and YouTube when `youtube` is set) carries every required attribution text verbatim (each attribution-licence credit's `attribution`, and the TMDB notice "This product uses the TMDB API but is not endorsed or certified by TMDB" whenever a credit is TMDB) in its caption (YouTube: the description) or in that platform's first comment. The packager writes it; the validator refuses a batch that lacks it; the Pi publishes the approved text unchanged.
- `disclosure`: `{aiGenerated, aiKinds, realisticSynthetic, note}`; `aiKinds` ⊆ script, voice, image, video, music, sfx; `aiGenerated` is true exactly when `aiKinds` is non-empty, and must be true when `render.models` lists an llm, tts, image, video or music model; `realisticSynthetic` is true only for realistic synthetic people, places or events (drives labels that only apply to realistic content).
- `video`, `cover`, `eligibility`: v1 rules.

### Project modules

- **scalargame** (`contract/projects/scalargame.py`): batch `projectData = {sourceSnapshotHash}`; episode `projectData = {game, difficulty, styleId, creative, evidence, music}` with the v1 rules (episodeId and contentId prefixed by the game, styleId names a motion style recipe of the batch, choices contain the answer once, spoiler gate, evidence sources, `uniqueAnswer`). Formats: the eight v1 formats (motion). The link is required and points at `https://www.scalargame.com/<path>`. Poll and answer reply allowed.
- **originals** (`contract/projects/originals.py`): batch `projectData = null`; episode `projectData = {subject: {kind: movie|book|story|original, title, year}, sources[], checks: {rights, garbage, visualQa}, reviewer, series: {seriesId, episode} | null}`; every check must be true; a recap needs at least one source and credits its footage; an animated short names its series. Formats `movie-recap`, `story-recap` (story/recap) and `animated-short` (story/series). The link is optional. No poll, no answer reply.

### v1 on the Pi

A v1 batch validates with the v1 rules forever. For views and policies the Pi reads a v1 episode as: project `scalargame`, `contentId = questionId`, engine `motion`, renderer not recorded, link `https://www.scalargame.com<deepLink>` with its `utmCampaign`, credits from `publication.credits` plus `music`, disclosure not declared (no AI label is applied). Duplicate protection keeps the ledger's `question_id` column, which holds the contentId; namespaces cannot collide, so nothing is migrated.
