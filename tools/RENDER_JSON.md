# `render.json` (engine → packager, version 1)

Every engine writes one `render.json` per rendered episode, in the folder that holds the episode's MP4 and cover. It is the only thing the shared packager (`tools/package.mjs`) reads from an engine; engines never write `batch.json`. It is not part of the batch contract (`contract/BATCH_CONTRACT.md`): contract v2 copies `models`, `costUsd`, `credits` and `disclosure` into each episode, copies `job.renderer` to `render.renderer`, and stamps `render.renderSha256` = sha256 of this file. The motion engine writes (and the Studio's browser export hashes) exactly `renderJsonText(doc)` from `engines/motion/pipeline/render-json-core.mjs`, so both give the same hash for the same document.

Check a file: `node tools/render-json.mjs <render.json>...` (exit 1 on any error; the packager runs the same check).

| Field | Type | Rule |
|---|---|---|
| `renderJsonVersion` | `1` | |
| `engine` | `motion` or `story` | |
| `route` | `recap`, `series` or null | null for motion; required for story |
| `kitVersion` | string | the engine's version label (motion: `kit-1`; story: `story-1`) |
| `project` | string | a project in `studio.json` |
| `episodeId` | string | `[a-z0-9-]+`, ≤ 80 characters |
| `createdAt` | UTC `YYYY-MM-DDTHH:MM:SSZ` | when the render was validated |
| `job` | object | engine-specific inputs the project's packager needs (motion: `revision`, `contentKey`, `contentId`, `styleId`, `musicBed`, `propsHash`, `coverFrame`, and `renderer`: `"render.sh"` for render.mjs jobs, with their `codeHash`, or `"web"` for the Studio's in-browser export, with the UI bundle's `bundleCommit`) |
| `video` | object | `file` (relative to this file's folder, no `..`), `sha256`, `bytes`, `durationSeconds`, `width`, `height`, `fps` (`num/den`), `videoCodec`, `audioCodec` (null when silent) |
| `cover` | object or null | `file`, `sha256`, `bytes` |
| `models` | list | `{role, id}` with `role` ∈ `llm`, `tts`, `image`, `video`, `music`, `asr`; every generative model that made something in the video |
| `costUsd` | number ≥ 0 | paid-API spend for this episode (0 for a motion render or a mocked run) |
| `costEstimated` | boolean | true when `costUsd` is (partly) an estimate rather than billed usage |
| `credits` | list | one entry per third-party, owner or generated asset in the video: `{kind, title, creator, sourceUrl, license, attribution, sha256}` |
| `disclosure` | object | `{aiGenerated, aiKinds, realisticSynthetic, note}` |

Credits:
- `kind` ∈ `footage`, `image`, `poster`, `music`, `sfx`, `font`, `voice`, `data`, `text`, `model`.
- `license` ∈ `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `OFL-1.1`, `Pexels`, `Pixabay`, `TMDB`, `Wikipedia-CC-BY-SA`, `owner`, `generated`, `public-domain`, `unknown`. `unknown` is recorded honestly (e.g. the story engine's stock fallback clips); the packager refuses it from contract v2 on.
- `CC-BY-4.0`, `CC-BY-SA-4.0`, `TMDB` and `Wikipedia-CC-BY-SA` need non-empty `attribution` text. `TMDB` attribution must contain "This product uses the TMDB API but is not endorsed or certified by TMDB".
- `creator`, `sourceUrl`, `attribution`, `sha256` may be null; `sourceUrl` is https when set; `sha256` is 64 hex characters when set.

Disclosure:
- `aiKinds` ⊆ `script`, `voice`, `image`, `video`, `music`, `sfx`; `aiGenerated` is true exactly when `aiKinds` is non-empty.
- `aiGenerated` must be true when `models` lists any `llm`, `tts`, `image`, `video` or `music` model whose output is in the video.
- `realisticSynthetic`: true only for realistic synthetic people, places or events (drives YouTube's label).
- `note`: one plain sentence for the reviewer (what is AI-made and what is not).
