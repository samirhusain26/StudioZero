# StudioZero studio plan (running record)

Status: **Phase 6 done** (2026-10-13): Scalargame batch `2026-10-b02` (32 episodes, contract v2, the b01 carry-forward fixes) is finalized and waits for the owner's upload on the Pi before the 2026-10-23 refill; Home and Studio › Overview show when approved posts run out and the date to approve the next batch by; the Learn loop counts Facebook reactions and exports each post's questionId (`tools/retro_stats.py`). Log §18; what is left: **Next** (end of this file). Originals stay on hold (owner, 2026-10-12).

Resume rule: read this file, then the section for the current phase. Locked owner decisions (§1) are not re-argued. The original brief is `docs/prompts/STUDIOZERO_CONSOLIDATION.md` in the marketing repo (untracked there; it moves here in Phase 1).

Appendices (public-safe):
- [plan/PI_CUTOVER.md](plan/PI_CUTOVER.md): full Pi cutover design (updater internals with file:line refs, migration script, verification, rollback).
- [plan/STORY_ENGINE_REVIEW.md](plan/STORY_ENGINE_REVIEW.md): old StudioZero review (endpoint map E1–E24, features F1–F26, bugs B1–B10, module map, CLI, cost data, dependencies).

Private (never committed; on the owner's Mac only): the hash list for the safety check `~/.config/studiozero/private-id-hashes.txt`, and `~/Personal/backups/2026-10-studiozero/phase0/` holds the detailed public-safety audit (`audit_report.md`, exact paths/lines of every identifier) and the masked scanner `scan.py`. Backups of both working folders (with ignored files) are next to it.

---

## 1. Locked owner decisions (2026-10-11)

1. StudioZero becomes the studio behind @studiozeroflow. Projects: **P0 `originals`** (recaps, AI series), **P1 `scalargame`** (marketing). A mixed content page, not only ads.
2. GitHub `samirhusain26/StudioZero` is **public**; nothing private becomes public.
3. Keep and build on the old StudioZero work (incl. the uncommitted multi-model work); both story routes stay.
4. Recaps may use stock footage and posters; every asset is credited in the contract (TMDB attribution where TMDB data/images are used).
5. One UI: a sixth Pi UI section **Studio** (revises D1 of `PI_UI_REDESIGN_PLAN.md`); Studio = the Make step of Make → Upload → Review → Schedule → Post → Learn.
6. Re-pointing the Pi to the new repo is approved, using the Pi's own scripts; never hand-edit `/opt/scalar-social/repo`.
7. Pi runtime names stay `scalar-social`; only the UI product name changes.
8. **Device compute (2026-10-12):** the Pi Zero 2 W (512 MB) only serves the Studio UI, stores the library, approves, schedules and publishes. Making runs on the device that opens the UI: motion episodes preview (Remotion Player) and export (Remotion client-side rendering, WebCodecs) in the browser, then upload to the Pi through the existing upload → validate → approve flow; the Python story engine runs as a worker agent on the owner's laptop. No spike first (owner: proceed). `render.sh` on the Mac stays available as the house-master path. New UI dependencies `@remotion/player`, `@remotion/web-renderer`, `@remotion/media` (pinned to the motion engine's Remotion version) approved with this plan.

## 2. Target architecture (summary)

- **Engine** = how (toolchain, render, media QA; no posting, no project rules): `motion` (Remotion, today's `studio/`), `story` (old StudioZero package; routes `recap`, `series`).
- **Project** = why/for whom (sources, fact/rights rules, voice, CTA, link policy, budget, mix share, goals): `originals`, `scalargame`.
- **Channel** = where (the @studiozeroflow accounts); publisher only.
- **Format** = a project's recipe on one engine, e.g. `scalargame/progressive-clues` (motion), `originals/movie-recap` (story/recap), `originals/animated-short` (story/series).
- Flow for every project: Brief → Make (engine, Mac) → Check → Package (shared packager → `batch.json`) → Approve (Pi) → Schedule (mix) → Post → Learn.
- Boundaries: engines write MP4 + cover + `render.json` (hashes, duration, resolution, models, costUsd, per-asset credits, aiGenerated + note) and never `batch.json`; `tools/` packager turns `render.json` + project captions into `batch.json`; `contract/` validates (v2, per-project modules); `projects/<p>/project.json` + root `studio.json` feed the prompt builder and Studio UI.
- Placement rule: code that must build with an engine's toolchain lives in that engine under `src/projects/<project>/`; content and rules live in `projects/<project>/`.

Target tree: as in the brief (`studio.json`, `docs/`, `contract/`, `publisher/`, `engines/{motion,story}/`, `projects/{originals,scalargame}/`, `tools/`, `library/`, `.claude/`).

---

## 3. Phase 0 findings

### 3.1 Public-safety audit (both repos, tracked trees + full history, custom masked pattern pass; gitleaks/trufflehog are not installed and were not installed)

**Must rotate: nothing.**
- Old StudioZero (public): no credential file (`.env`, `env.yaml`, `assets/creds/*`, token/client-secret/service-account JSON) was ever committed in its 23 commits. The commits "Fixing OAUTH creds", "Base64 update" and "Token troubleshooting" add code that *reads* tokens; no values. `deploy.yml` references secrets by name only. Every env template is placeholder-only. No long Base64 blobs anywhere.
- GitHub Actions logs of the 7 old Cloud Run deploy runs have expired (API answers 410 Gone), so the multi-line JSON secret masking risk is closed. GitHub shows 1 branch (`main` = local `dc12780`), 0 forks.
- Hygiene (optional, owner): the Google OAuth client/refresh token, service account key and Drive/Sheets access used only by the retired Cloud Run/Drive/Sheets features can be revoked once Phase 1 retires that code.

**Blockers for importing the marketing tree publicly** (no secrets; infrastructure IDs, real account IDs, personal data):

| # | Finding | Where (classes; exact lines in the private audit) | Proposed action |
|---|---|---|---|
| I1 | Real Tailscale host name of the Pi | publisher code (`ui_server.py` `DEFAULT_ORIGIN`), the UI unit's `--allowed-origin`, an installer, a test, guide pages, publisher docs, top-level docs, and the **built static bundle** | Parameterize (unit reads `SCALAR_UI_ORIGIN` from a root-owned `/etc/scalar-social/ui.env`; no default in code), placeholders in docs/guide, rebuild `publisher/app/static`. Note: `*.ts.net` names also appear in public Certificate Transparency logs, so this is hygiene, not secrecy. |
| I2 | `publisher/config.example.json` is not placeholder-only (real Buffer channel IDs, X user ID, YouTube channel ID, the owner's personal Facebook profile URL and display name) | config.example.json | Placeholders only. |
| I3 | Real platform IDs hardcoded in app code (Cloudflare account ID and Pages project; Buffer channel IDs, X, YouTube, Facebook Page, Threads, Bluesky IDs). `configure_paused.EXPECTED` is the identity pin that `activate`, `autopilot` and `approval_bind` verify against. | publisher/app | **Owner decision.** Recommendation: keep them (none grants access; profile IDs are public on the profiles; Cloudflare says account IDs are not secret) to avoid touching the live autopilot's identity check. Alternative: move them to root-owned `/etc/scalar-social/config.json` (behaviour change on a live path; needs its own tests and a careful ship). |
| I4 | Operational test records / handoffs with real post permalinks, app/Page IDs, granted scopes, personal notes | 8 files in `publisher/docs/` (first-post test, channel expansion, handoff, platform matrix, Instagram direct setup, profile review, Buffer support request, TikTok application draft) | Remove from the tree before the import (they stay in the private archive's history). Keep generic docs (PI_UI, SCHEDULE, SELF_UPDATE, MEASUREMENT, …) after redaction. |
| I5 | A project contact Gmail (not the owner's main address) | two of the I4 files | Goes with I4. |
| I6 | Pi access details: Pi host/user `.local` name, `/home/<user>` paths, SSH key path, "passwordless sudo" | sync-pi.sh usage line, guide pages, docs, CLAUDE/AGENTS, bundle | Use the `scalar-pi` alias / `$SCALAR_PI` / `<user>@<pi>.local` placeholders; drop key path and sudo statements from public CLAUDE/AGENTS. |
| I7 | **Future Whenabouts puzzles**: `library/_sources/2026-10-06-3921b9e/public/puzzles/` has 1,112 daily puzzles to 2029-05, **936 future-dated**; the snapshot also holds private game-repo data and `dailySelection.mjs`. The game repo is **private** (checked); the live site serves the shards. | `library/_sources/**` (60 files, 8.7 MB) | Keep out of the public repo (§5). |
| I8 | Old private repo name in the updater, `bootstrap-git.sh`, tests, guide | publisher | Updated by the cutover (§7). |
| I9 | Absolute Mac home paths in historical docs/prompts; first name "Samir" in skills/guide | docs, `.claude` | Redact paths; first name is acceptable. |

**Rights**
- Marketing: every committed music bed is listed in `beds.json` (90 CC0 from OpenGameArt/HoliznaCC0 with artist and page; **6 owner-supplied Gemini tracks**, `licenseIndependentlyVerified: false`); 27 SFX are procedural (`make_sfx.py`); 5 font families each ship the OFL text; World Bank data (CC BY 4.0) needs attribution in the snapshot README. Recommendations: a root `CREDITS.md`; do not publish the 6 Gemini beds as files (redistribution terms unverified; they are retired for new batches anyway) — keep them local/ignored.
- Old StudioZero (already public): `assets/basevideos/video1..24.mp4` (656 MB, unknown origin) and 20 Pixabay-pattern `assets/music/*.mp3` (81 MB) are tracked with **no licence or source record**. The Pixabay Content License forbids standalone redistribution. Phase 1 untracks both (files stay local, ignored). They remain in public history; removing them from history would need a rewrite, which the standing rules forbid — flagged for the owner only.

**Old StudioZero hygiene before its next commit**: add `.playwright-mcp/` to `.gitignore` (page snapshots are not ignored today); untrack the two tracked `.DS_Store`; `.gitignore` ignores all of `.claude/` — narrow it to `.claude/settings.local.json` so skills/agents can be tracked.

### 3.2 Pi health (read-only check, 2026-10-11 17:00 ET) — **precondition for the cutover**

- `scalar-social.service` (publisher, fail-closed) has exited 2 on every 15-minute run since 2026-10-10 evening: `ok: false` because two jobs (Instagram, YouTube) are `uncertain` and need reconciliation. Jobs: 20 confirmed, 155 ready, 2 uncertain. The monitor reports `healthy: false` (issues: `publication_needs_review`, `threads_token_renewal_failed`).
- `scalar-social-threads-refresh.service` failed at 04:30 (credential preserved).
- Owner territory (reconciling posts, platform tokens). The cutover waits for a healthy baseline.
- Facts: Pi HEAD `3630621` = the last publisher/contract change (local main `4d1cdff` is one studio-only commit ahead; `publisher/` and `contract/` trees identical); last update check green; no `PAUSED`; autopilot 05:15/17:15 ET; ~225 MB RAM available; Python 3.13.5; coreutils has `mv --exchange`. Old copied install (`/opt/scalar-social/scripts`, `/opt/scalar-social/ui`) still present, unused.

### 3.3 Mac toolchains and local data

- **`studio/node_modules` and `studio/.venv` are missing** in the marketing repo (lockfile and requirements are present). Motion `tsc`, rendering and the Python audio tools cannot run until they are reinstalled from the existing lockfile (not a new dependency; needs network). `publisher/ui/node_modules` is present.
- Ignored local data and where it lands (moved, never deleted; venvs recreated, not moved):

| Today | Size | Lands at |
|---|---|---|
| marketing `library/2026-10-*/{videos,covers,review}` | 125 MB | `library/` (same paths) |
| marketing `library/_dev/` | 279 MB | `library/_dev/` |
| marketing `studio/music/sources/` | 920 MB | `engines/motion/music/sources/` |
| marketing `studio/.audio-work/` | 1.0 GB | `engines/motion/.audio-work/` (scratch; owner may later drop) |
| marketing `studio/out/` | 145 MB | `engines/motion/out/` (may show tokens; never commit) |
| marketing `studio/sfx/` sources | 23 MB | `engines/motion/sfx/` |
| marketing `publisher/ui/node_modules`, `dist/` | 190 MB | same paths (or `npm ci`) |
| StudioZero `.env`, `env.yaml`, `assets/creds/` | small | `engines/story/` local, ignored (`env.yaml`, `assets/creds` only needed by retired Cloud Run/Drive; archive them in the backup, owner decides) |
| StudioZero `assets/basevideos`, `assets/music` | 737 MB | `engines/story/assets/…` (untracked, ignored, provenance unknown) |
| StudioZero `output/` | 144 MB | `engines/story/output/` |
| StudioZero `.playwright-mcp/`, `StudioZero.app/` | small | dropped from the tree (kept in the backup) |

### 3.4 Batches

No unfinalized motion batch exists (only `library/_dev` scratch). `2026-10-pilots` and `2026-10-b01` are finalized and immutable. Moving `studio/` → `engines/motion/` changes the `codeHash` paths (`render.mjs` hashes repo-relative paths), so any old job reads `staleKit` — expected and harmless. `lib.mjs` finds the game repo as `../scalargame` from the new location without changes.

### 3.5 Old StudioZero (details: plan/STORY_ENGINE_REVIEW.md)

- Uncommitted work (+1165/−193 in 20 files plus new `budget_guard.py`, `video_client.py`, `video_models.py`, `steps/set_designer.py`, `tools/model_compare.py`): an 11-model registry in 3 tiers (Veo via Gemini API, fal.ai), unified video client with fallback, budget guard, set-designer step, model-aware director prompts, dashboard settings. All 40 Python files compile; all internal imports resolve; no tests exist.
- Bugs to fix before any paid run: **B1** recap from the dashboard never finishes (re-generates the script after the review gate, paid, forever); **B2** Pause does not stop the worker (spend continues; a second thread can start); **B3** series clips from fal.ai have no audio and there is no voice step; **B4** the budget guard resets per episode/retry and counts video estimates only; **B5** settings changes need a restart, `FAL_KEY` from settings never reaches fal; **B6** retries can re-submit a paid generation, fallback switches model without a budget re-check; **B7** set_designer missing from the UI step list; **B8** registry price/description mismatches, "change model" is global; **B9** dead Vertex path; **B10** API key in a download URL.
- Retire without breaking routes: `batch_runner`, `cloud_services`, `marketing` (Groq captions), `app`, `server_launcher`, `veo_client`, token scripts, Docker, `deploy.yml`, `StudioZero.app`, `launch.sh` (first remove `cli.py`'s top-level `batch_runner` import). Keep `headless.py` (seed of the agent job runner), `project_manager.py`. `narrative.py` still imports Groq as a script fallback.
- Cost data for `render.json`: today only series video cost (estimate) is recorded; recap records nothing; no token usage capture. Credits available: Pexels URL + photographer per scene, TMDB poster path; missing: Wikipedia page URL, per-clip model after fallback, music/basevideo licences.

---

## 4. Repo strategy (recommendation)

As the owner's default, with one addition (**I-prep**) the audit makes necessary:

1. Public `samirhusain26/StudioZero` keeps its history. Phase 1 commits the old WIP to a branch, merges, tags `legacy-final`.
2. **I-prep (in the private marketing repo, normal ship flow):** one commit that makes `publisher/` and `contract/` public-safe *and* ships cutover Step 1 (updater accepts the StudioZero origin; `migrate-origin.sh`): I1 parameterization (Pi `ui.env` written first), I2 placeholders, I4/I5 doc removals, I6 redactions in publisher docs/guide/scripts, static bundle rebuilt. Commit → push → `sync-pi.sh`. This is within the standing approval (publisher/contract shipping). After it, **`publisher/` and `contract/` are frozen** until the cutover.
3. **One audited import commit** into StudioZero: the marketing tree at the I-prep commit, minus the exclusion list, with top-level docs redacted (I6/I9) and the public-safety check passing. Exclusions: `library/_sources/**`, the 6 Gemini beds, historical prompts with private paths (`docs/prompts/**` except the consolidation prompt, `docs/NEXT_SESSION_PROMPT.md`) — kept in the private archive. The import's `publisher/` and `contract/` tree hashes must equal the Pi's.
4. `scalargame-marketing-plan` stays private, archived (not deleted: deleting it would delete the Pi's deploy key) after the cutover is verified.
5. No history rewrite, no force-push anywhere.

### 4.1 `library/_sources` (decision needed)

- **A (brief's default):** ignored in StudioZero, kept locally and in the private archive. Risk: new snapshots (frozen evidence for every future batch) would live only on this Mac and its backups.
- **B (recommended):** a small private repo (e.g. `studiozero-private`) cloned into an ignored folder, holding `_sources/`, the excluded ops records and future private evidence. Snapshots stay versioned and off the public repo. Needs a new GitHub repo (owner OK).
- Either way: `node check.mjs` (path updated) must still reproduce `questionsHash 5ab19d44…` locally.

### 4.2 LICENSE (decision needed)

- **None** (all rights reserved; code visible, not reusable). Simplest; nothing to police.
- **MIT for code**, with `CREDITS.md` listing asset licences (CC0 beds, OFL fonts, procedural SFX) and an explicit carve-out: brand/profile assets and channel names are not licensed. Good for a portfolio repo.
- Recommendation: MIT + carve-out if the owner wants the code reusable; otherwise none.

### 4.3 Packager regression definition

`batch.json` stamps `createdAt` and `generator.repoCommit/dirty`, so "byte-identical" means: re-package the 2026-10 batches into a temp dir with `--created-at` and `--commit` pinned to the finalized values (new packager flags) and `git diff --exit-code` against the finalized `batch.json`. The finalized folders are never written.

---

## 5. Contract v2 (draft for owner approval)

Principles: v1 stays valid forever (dispatch on `schemaVersion`; the v1 code path is unchanged); one validator module on Mac and Pi (stdlib); project-specific rules in `contract/projects/<project>.py` (synced to the Pi, so the Pi checks everything); the Pi publishes exactly the approved text with `{link}` expanded and nothing else changed.

### 5.1 Batch

| Field | Type | Rule |
|---|---|---|
| `schemaVersion` | `2` | |
| `batchId` | string | v1 rule (`YYYY-MM-<slug>`; Pi-created forms unchanged) |
| `createdAt` | UTC `…Z` | v1 rule |
| `project` | string | a registered project (`contract/projects/`); **one project per batch** (one brief, one retro, one validator pass) |
| `generator` | `{repoCommit, dirty}` | v1 rules (`assetKitVersion` moves to each episode's `render`) |
| `styleRecipes` | list `{styleId, engine, version, summary}` | may be empty; the project decides if styles are required |
| `projectData` | object or null | batch-level project fields (scalargame: `sourceSnapshotHash`) |
| `episodes` | list (≥ 1) | unique `episodeId`s |

### 5.2 Episode (core)

| Field | Type | Rule |
|---|---|---|
| `episodeId` | string | `<prefix>-<format-slug>-<nnn>`; prefixes declared by the project (scalargame: its games, e.g. `scalar-clues-001`; originals: `originals-…`) |
| `contentId` | string | **duplicate key**, generalizes `questionId`. `<namespace>:<id>`; namespaces declared by the project and unique across projects (scalargame: `scalar:`, `continuum:`, `whenabouts:`, `tectonic:` — **identical to v1 questionIds**, so v1 and v2 share the ledger; originals: `originals:`) |
| `revision` | int ≥ 1 | v1 rule |
| `format` | string | in the project's format list |
| `language` | tag | v1 rule |
| `render` | `{engine, route, kitVersion, renderSha256, models[], costUsd}` | `engine` ∈ `motion`, `story`; `route` (`recap`, `series` or null); `renderSha256` = sha256 of the engine's `render.json`; `models` = list of `{role, id}` (llm, tts, image, video, music); `costUsd` ≥ 0 |
| `experimentId`, `variantId` | text or null | v1 rules |
| `tags` | list of `[a-z0-9-]` | optional labels for Learn |
| `video`, `cover` | objects | **v1 rules unchanged** (paths, hashes, ffprobe re-measure, H.264/yuv420p/9:16/AAC, ≤ 24 MB, fast-start) |
| `link` | null or `{url, utmCampaign}` | `url` https; `{link}` in text allowed only when non-null; expands to `url` + UTM (`utm_source=<platform>`, `utm_medium=organic_social`, `utm_campaign`, `utm_content=<episodeId>`). The project decides whether a link is required |
| `publication` | object | v1 fields minus `deepLink`/`utmCampaign`/`credits`: `captions` (per platform), `youtube`, `altText`, `hashtags`, `poll`, `firstComment`, `answerReply`; v1 length/placeholder/link-platform rules; the project may forbid `poll`/`answerReply` |
| `credits` | list | one entry per third-party or generated asset: `{kind, title, creator, sourceUrl, license, attribution, sha256}`; `kind` ∈ footage, image, poster, music, sfx, font, voice, data, text, model; `license` from a fixed list (CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0, OFL-1.1, Pexels, Pixabay, TMDB, Wikipedia-CC-BY-SA, owner, generated, public-domain); licences that require attribution require `attribution` text |
| `disclosure` | `{aiGenerated, aiKinds[], realisticSynthetic, note}` | `aiKinds` ⊆ script, voice, image, video, music, sfx; `realisticSynthetic` drives platform labels that only apply to realistic content (YouTube) |
| `eligibility` | object | v1 rules |
| `projectData` | object | validated by the project module |

**Attribution rule (recommended change from the brief's "publisher renders credits"):** the packager writes required attribution text into every platform text that will publish (caption, YouTube description, or that platform's first comment where length forbids the caption), and the validator refuses a batch where any platform that would post lacks a required attribution. TMDB's notice ("This product uses the TMDB API but is not endorsed or certified by TMDB") is enforced whenever a credit has `license: TMDB`. Why: the owner approves the exact text that posts (the approval hash covers it), caption limits are checked before approval, and the Pi keeps its "publish exactly the approved text" invariant. The publisher's Phase 4 job becomes verifying, not composing.

**AI labels:** the Pi maps `disclosure` to each platform's label where its API or Buffer supports it (YouTube synthetic-content flag, TikTok AIGC flag, Meta AI info); where unsupported it records that in the job (Phase 4 verifies each API).

### 5.3 Project modules

- `contract/projects/scalargame.py`: `projectData` = `{game, difficulty, styleId, creative, evidence, music}` with the v1 rules (answer/choice/spoiler gate, evidence sources, `uniqueAnswer`); batch `projectData.sourceSnapshotHash` required; link required (scalargame.com deep link); formats = the eight v1 formats.
- `contract/projects/originals.py`: `projectData` = `{subject: {kind: movie|book|story|original, title, year}, sources[], checks: {rights: true, garbage: true, visualQa: true}, reviewer, series: {seriesId, episode} | null}`; formats `movie-recap`, `story-recap`, `animated-short`; link optional; required credits: every footage/poster/music asset; `disclosure.aiGenerated` must be true when `render.models` lists any generative model.

### 5.4 v1 → v2 rules

- A v1 batch validates with today's code, forever. Regression tests validate both finalized 2026-10 `batch.json` documents (document checks, no media) on every run.
- The Pi normalizes a v1 episode as: `project: scalargame`, `contentId = questionId`, `render.engine = motion`, `link = {url: https://www.scalargame.com + deepLink, utmCampaign}`, credits from `publication.credits` strings plus `music`, `disclosure.aiGenerated = null` ("not declared"; no label), `projectData` = the v1 quiz fields.
- Per-project duplicate protection keeps the existing ledger column (`question_id` holds `contentId`); namespaces cannot collide, so no data migration.
- The Mac packager keeps writing **v1 for scalargame** until the Pi runs the v2 validator (Phase 4); then new scalargame batches may move to v2.

---

## 6. Catalog, Studio agent, proxy (Phase 2–3 design notes)

(Revised by decision 8: motion making moves into the browser; the worker agent below is for the Python story engine, and paid API calls stay in that worker, so keys never reach a phone or the Pi UI. Phase 3 prompt: `docs/prompts/PHASE3_SESSION.md`.)

- **Catalog source: a generated, committed `publisher/catalog.json`** (written by `tools/export-catalog.mjs` from `studio.json`, `projects/*/project.json`, the motion engine's template/style/bed registries and the story engine's route/model registry; a `--check` mode fails when stale, run with `check:static`). The Pi serves it at `/api/catalog`; the prompt builder and Studio tab read it; Pi Python reads it for mix-policy defaults and link policy. Why: the Pi's sparse checkout has only `publisher/` and `contract/`, so this needs no sparse-path change; it works with the Mac asleep; the UI needs no rebuild when only the catalog changes; and the engines' own registries generate it, so the builder never offers something an engine cannot render. `GAMES`/`FORMATS` in `publisher/ui/src/api/types.ts` and `ui_views.GAMES` become catalog-derived.
- **Pi proxy needs its own unit.** The UI unit has `IPAddressAllow=localhost`, `IPAddressDeny=any`, `MemoryMax=96M` (no outbound network by design). Proposal: `scalar-social-studio-proxy.service` (stdlib) allowed to reach only the Mac's tailnet address (set in a Pi-local drop-in, never in git), listening on a unix socket; `ui_server` forwards `/api/studio/*` to it after its normal passcode/session checks. Route allowlist, size caps, timeouts, Range streaming in chunks, "Mac studio offline" response. The bearer token for the Mac agent reaches the proxy via `LoadCredential`.
- **Mac studio agent:** FastAPI (existing dependency) evolved from `server.py`, bound to `127.0.0.1`, exposed on the tailnet through Tailscale Serve on the Mac, bearer token, opt-in `launchd` agent, polling JSON (no WebSockets), cancel flag (fixes B2), per-project cost ledger (fixes B4), paid actions require a server-side budget check plus a confirmed cost estimate.
- Old dashboard parity: F1–F3, F5–F22, F25 port; F4 (Sheets), F23 (plaintext API keys), F24 (Integrations), F26 (auto-open browser) drop. Endpoint map E1–E24 in the appendix.

## 7. Pi cutover (summary; full design in plan/PI_CUTOVER.md)

- An in-place re-point is impossible: the updater's origin allowlist is exact-match, and its ancestry check plus `--ff-only` refuse an unrelated history (`diverged`).
- **Step 1** (ships in I-prep): updater and `bootstrap-git.sh` also accept `git@github.com-scalar:samirhusain26/StudioZero(.git)`; tests: StudioZero accepted, look-alikes refused, unrelated history refused as diverged; `migrate-origin.sh` added.
- **Step 2** `migrate-origin.sh --commit <sha> [--dry-run|--rollback]` (root, idempotent): fresh partial+sparse clone into `repo.next` as the update user with the same root-owned ssh config and key; verify `publisher/`+`contract/` tree hashes and `diff -r` equal the running checkout; prove the key cannot push; snapshot state (hashes only); wait for a quiet minute; take `runner.lock`; `mv --exchange` (atomic); rewrite `units-applied.json`; restart the UI only (does **not** run `apply-units.sh`, which would re-enable timers); automatic rollback on any failure. `/etc/scalar-social`, `/var/lib/scalar-social`, `PAUSED`, timers are untouched.
- **Window:** 09:00–15:00 or 19:00–03:30 ET, at least 30 min from autopilot and the daily post slot (the script enforces it). Dry run first.
- **Verify:** origin, trees, sparse/partial config, ownership/modes, unit states equal to before, UI health, update check green on StudioZero, next autopilot scheduled, config/approved-manifest hashes unchanged, `sync-pi.sh` in sync.
- **Deploy key:** the existing read-only key can already read the public StudioZero (verified with `ls-remote`), so the cutover needs no GitHub change. After verification, move the key's attachment to StudioZero (read-only) with owner OK; never delete the old repo.
- Preconditions: Pi publisher healthy (§3.2), branch protection on StudioZero `main`, `publisher/`/`contract/` frozen since I-prep.

## 8. Public-safety rules (to land in `docs/PUBLIC_SAFETY.md` and CLAUDE/AGENTS in Phase 1)

Never committed: credentials, tokens, passcodes, deploy keys, `.env*`, `env.yaml`, `assets/creds/`, `publisher/config.json`; media, renders, `out/` and QA screenshots; music/SFX without a recorded licence; Pi/tailnet host names, `*.ts.net`, IP addresses, personal phone/address/email details; unreleased or future game answers; private game-repo content beyond the snapshot rules. Required: `tools/public_safety_check.py` (stdlib; derived from the audit scanner; calls git/grep directly because the shell hook rewrites their output) run before every push and in CI if CI exists (CI uploads nothing); `config.example.json` placeholders only; docs name hosts by alias (`scalar-pi`).

---

## 9. Phase checklist

### Phase 0 — audit and plan ✅ (2026-10-11)
- [x] Backups of both folders incl. ignored files (`~/Personal/backups/2026-10-studiozero/`, 2.8 GB + 1.6 GB)
- [x] Ignored-data inventory and landing plan (§3.3)
- [x] Public-safety audit, both repos, trees + history (§3.1)
- [x] Repo strategy (§4)
- [x] Pi cutover design (§7, appendix)
- [x] Unfinalized motion batches: none (§3.4)
- [x] This plan, contract v2 draft, parity list
- [x] **CHECKPOINT 1** answers (§10; contract v2, repo strategy and cutover approved 2026-10-11)

### Phase 1 — consolidation (no behaviour change)
- [x] Old StudioZero: hygiene (§3.1), WIP to a branch, merged, tagged `legacy-final` (b6e4962)
- [x] Motion toolchains reinstalled: `node_modules` (lockfile) and `.venv` (python3.12; numpy, scipy, librosa, soundfile, pyloudnorm, Pillow). Story engine venv: not created (whisper/torch; on first story run)
- [x] I-prep in the marketing repo, shipped: 2a97346 (identity pins → Pi config) and 213dc9e (tailnet origin → `ui.env`, docs/guide redacted, ops records removed, updater accepts StudioZero, `migrate-origin.sh`); Pi on 213dc9e; **publisher/ + contract/ frozen**
- [x] Retire duplicates (§3.5) in StudioZero (d82f37e)
- [x] `src/` → `engines/story/` (ac49364); audited import commit (38254f4; publisher/contract trees equal the Pi's)
- [x] `studio/` → `engines/motion/`, shipped through the new origin after the cutover (contract/library_contract.py falls back to `studio/node_modules/.bin/remotion` for ffprobe on the Mac; that path fix ships with the move as the first update through the new origin)
- [x] Move ignored local data (§3.3) by rename (finalized batch media, `_dev`, toolchains, music/SFX sources, story assets/output/.env); venvs: story and motion after the move
- [x] Swap folders: `StudioZero` = new repo, `StudioZero-old-2026-10` kept; marketing checkout moved to `scalargame-marketing-old-2026-10` (private archive working copy)
- [x] Game repo: cf46e1d drops the `/marketing/` ignores (exact revert of 8830163's config lines) and adds the Marketing section to CLAUDE/AGENTS; **not pushed** (needs owner OK; local lint/Vitest not run: the game repo has no node_modules on this Mac, CI runs them)
- [x] CHECKPOINT 2 (owner: push + protect, game repo push, fix the Pi and cut over now, accept the `scout` name)
- [x] Branch protection on StudioZero `main` (no force-push/deletion, admins included); `legacy-final` tag pushed
- [x] Deploy key on StudioZero (read-only, push probe refused, update check green); `scalargame-marketing-plan` archived; the Pi's rollback copy removed (2026-10-12)
- [x] Pi cutover 2026-10-11 23:03Z (`migrate-origin.sh`): dry run green, swap, check green, units/PAUSED/config/schedule unchanged; first normal update through StudioZero (17894f6) delivered
- [x] All suites green; `check.mjs` reproduces `5ab19d44…`; regression diff clean; safety check green; local = GitHub = Pi
- [x] CLAUDE/AGENTS rewritten; memory copied to the StudioZero memory folder (pointer left in the old one); `~/CLAUDE.md` projects-table row applied (2026-10-12)
- [x] Old Mac folders deleted after checking the backups (2026-10-12); post-cutover clean-up d983053 (bootstrap and guide name StudioZero)

### Phase 2 — layout, manifests, packager (no behaviour change; contract stays v1)
- [x] Owner follow-ups (§13) done: deploy key, archive, rollback copy, old folders, `~/CLAUDE.md`, bootstrap/guide clean-up (d983053)
- [x] `studio.json`; `projects/originals/project.json`, `projects/scalargame/project.json` (formats, sources, link/CTA policy, caption defaults, budget, mix share, checks)
- [x] Placement rule applied: the quiz kit moved `engines/motion/src/episodes/` → `engines/motion/src/projects/scalargame/` (stills byte-identical before/after; `codeHash` paths changed, so older jobs read `staleKit`, as expected). The Scalargame pipeline stays in `engines/motion/pipeline/` (optional move skipped: its render/QA half is engine work; its content now lives in `projects/scalargame/`)
- [x] `render.json` v1 (`tools/RENDER_JSON.md`, checker `tools/render-json.mjs` + `node --test` cases); motion writes it on validation (`render.mjs` → `pipeline/render-json.mjs`)
- [x] Shared packager `tools/package.mjs` (+ `projects/scalargame/package.mjs`); `batch.mjs` is a wrapper; validates after writing; `--created-at/--commit/--dirty` pins
- [x] Packager regression `tools/package-regression.mjs`: both finalized 2026-10 batches re-packaged byte-identical and valid (finalized folders only read)
- [x] Catalog `tools/export-catalog.mjs` → committed `publisher/catalog.json`; `--check` runs in `check:static` (and `build:static` regenerates it)
- [x] Instagram first comments auto-confirm (ea31a8e): see §14
- [x] Story engine: venv (python3.12, requirements only), `--headless` for both routes, mocked $0 smoke test (34 tests), `render.json` per recap/episode, `registry.json` (single source for video models), B4/B6/B8 fixed, B2/B10 partly (see §14)
- [x] Docs, skill, agent, memory; all checks green; local = GitHub = Pi

### Phase 3 — Studio tab, device compute, story worker ✅ (2026-10-12; log §15)
- [x] Catalog API (`GET /api/catalog`) + prompt builder mode 1 (ca7f969)
- [x] Studio tab (sixth section), Make a batch moved into it (dbfebad)
- [x] Motion in the browser: Pi asset streaming + sparse widening (686c53c), kit in the UI, `@remotion/media` audio (437170d), Player preview, `renderMediaOnWeb` export, browser QA, IndexedDB resume, `render.json` with `job.renderer: "web"`, shared packager cores (1291a0b), upload through the existing flow (9bb1ddb, 8407d65)
- [x] Story worker agent (`engines/story/src/agent.py`), Pi proxy (`publisher/app/studio_proxy.py`, `scalar-social-studio-proxy.service`), Story jobs pages; B1, B2, B5 fixed in the agent
- [x] Old dashboard parity (written check below); `server.py` and `static/` retired
- [x] Prompt builder mode 2 (`#/studio/new`: new format, style or project → Claude Code prompt for the template + one pilot, previewed in Studio › Export's Player or Story renders)
- [x] build/check static, Pi memory and latency, security review (`plan/PHASE3_SECURITY_REVIEW.md`, two rounds, resolved), guide pages
- [x] Plan status, memory, `docs/prompts/PHASE4_SESSION.md`

**Old dashboard parity** (features F1–F26 and endpoints E1–E24 of `plan/STORY_ENGINE_REVIEW.md` §1; UI = Studio › Story jobs, `publisher/ui/src/views/studio/Story*.tsx`; API = `engines/story/src/agent.py` behind the Pi proxy):
- [x] F1 job list (status badge, pulse while running, delete with a confirm; the API needs the id as confirmation and refuses while running) · E3, E6
- [x] F2 kind picker (recap / animation series) · E4
- [x] F3 recap from a typed title. The wizard's `validate_input` + random fallback is **not** added: it is a paid Gemini call before any estimate (the headless path skips it too); the review gate (F14) shows what the script made of the title
- [x] F4 **dropped**: Google Sheets is retired (E7 dropped)
- [x] F5 series form (name, brief, 1–10 episodes, tier badge with a link to Story settings)
- [x] F6 "Surprise me" on Gemini (`POST /studio/ideas/random`, needs its own confirmation; E8 was Groq)
- [x] F7 Start / Continue / Retry show the worker's signed estimate first; the run carries it back; budget re-checked against the spend ledger (428 without, 409 when changed or over budget, 403 while paid runs are off) · E11
- [x] F8 live log by polling (`…/events?since=`), All / Steps / Errors, follow, "last update" · E13 (WebSocket → polling)
- [x] F9 step rail: pre-production, then per episode director, **set designer** (B7), scene generator, editor; duration, error, file count · E18 (state trimmed: no host paths)
- [x] F10 step files: images, clips, readable JSON for story/episodes/sheets/shots/layouts · E17, E10 (Range through the proxy)
- [x] F11 info panel (kind, episodes, steps done, time, clips/files, dates)
- [x] F12 budget panel from the job's spend ledger (not from WebSocket messages)
- [x] F13 tier badge on the new-job form and the job page (per-job model) · E20
- [x] F14 recap review gate: edit the JSON, approve; Continue narrates exactly the approved script (**B1** fixed: `pipeline.run(approved_script=…)` skips script generation) · E9
- [x] F15 scene failed: error, editable prompt with word count, model for this job only (B8 part), retry / edit / skip / change model; each decision returns a new estimate and runs only after it is confirmed · E12
- [x] F16 video polling indicator (latest `veo_polling` line while running)
- [x] F17 Cancel run with real cancellation: before the next step and, in the scene generator, before the next clip's paid submit (**B2** fixed) · E14
- [x] F18 error state with Retry (through the estimate)
- [x] F19 renders library from `render.json` (cover, play, cost, credits, download) · E15, E16
- [x] F20 quality presets with the detected preset or "Custom"
- [x] F21 model pickers; changes apply to the next run without a restart and `FAL_KEY` reaches fal (**B5** fixed: `Config.reload_settings` reloads every model and the key, `export_fal_key`) · E19–E21, models part of E22–E23
- [x] F22 video tier cards, per-model cards ($/s, resolution, length, audio, reference images, ~$/episode), budget per job, auto-downgrade
- [x] F23 **dropped**: keys stay in the laptop's `.env`; Story settings shows set / missing only (credential parts of E22–E23 dropped)
- [x] F24 **dropped**: Integrations (Sheets) retired
- [x] F25 stale "running" jobs reset to paused at agent start · E24
- [x] F26 **dropped**: no browser auto-open (the Pi UI is the front end; E1, E2 dropped)

### Phase 4 — contract v2 + publisher ✅ (2026-10-12; log §16)
- [x] Validator v2 (615d5cc, 6908515): dispatch on `schemaVersion` (v1 path unchanged), `contract/projects/{scalargame,originals}.py`, licence list, attribution rule, `render.renderer` (owner-approved addition); both finalized batches validate on every run; `BATCH_CONTRACT.md` v2 section
- [x] Packager v2 (529b2e9): shared cores write v1 or v2, `renderSha256`, unknown licences refused, attribution in every caption; Originals core; browser = Mac byte for byte (Vitest); regression byte-identical (pinned to v1)
- [x] Pi importer + duplicate protection (d431b96): v1 and v2 in one library, `question_id` = contentId, no migration; the generator verifies attributions post; old vs new code gave the identical draft on the Pi's live data
- [x] Mix policy (79f5541): `project-mix` ordering, autopilot and UI use it only when the catalog has targets; with null targets inputs and drafts are byte-identical
- [x] AI labels (f3a33d0): verified field per platform (`publisher/docs/PLATFORM_MATRIX.md` "AI labels"); job payload records applied / not-needed / not-supported; v1 payloads unchanged
- [x] UI and Learn (ea8808d): Made with (project, engine, renderer, models, cost, credits, disclosure), project filter, Learn groups by project/engine/format/renderer, per-project runway, guide; Scalargame `project.json` → contract v2 (owner); smoke + journey e2e follow the one-tap approval (owner OK)
- [x] Scratch v2 batch (real media) + a v1 batch imported, approved and drafted end to end, locally and on the Pi (throwaway state); build/check static; Pi memory; security review (§16)
- [x] Plan status, memory, `docs/prompts/PHASE5_SESSION.md`

### Phase 5 — Originals back online ✅ (2026-10-12; log §17)
- [x] Story engine → contract-ready render.json ($0, 7bb6d07): contract ids at staging (`tools/stage-story.mjs`, `originals-<format>-<nnn>`), known licences only (CC0 music from the motion corpus or none, no local stock fallback, OFL caption font), MP4 conformed to the contract media rules, LLM/image/TTS priced into the spend ledger and `costUsd`, uncertain submits counted; the $0 smoke test stages, packages and validates both routes as v2 batches
- [x] Bugs that blocked paid runs (7bb6d07): B3 (normalised clips, native-audio policy), B7/B8 rest (every video model verified against fal.ai/Gemini, per-model request maps, real Seedance prices, price-ordered fallback, Sora unverified and never called), B9 (dead Vertex/Drive config), B10 rest, ledger gaps
- [x] `/originals` playbook skill, `originals-fact-checker` agent, `ORIGINALS_BRIEF.md`, `--estimate` (a7208cf); $0 rehearsal on a real render (`library/_dev/2026-10-o901`)
- [x] Prompt builder Originals path and guide pages (6cb10e7)
- [x] First Originals brief planned: `library/_briefs/2026-10-o01.md` (waiting for the owner)
- [x] build/check static, e2e, Pi throwaway import of the v2 scratch batch next to a v1 batch, Pi health, security review (§17)
- [x] Plan status, memory, "After Phase 5" (no further session prompt)

### Phase 6 — Scalargame marketing at a steady cadence ✅ (2026-10-13; log §18)
- [x] Next batch `2026-10-b02` before the runway ends: brief (Checkpoint 0: 32 + 8 spares, pilots inside the batch), snapshot `2026-10-12-cf46e1d`, independent fact-check (three rounds, all pass), Checkpoints 1–3, finalized 2026-10-13T02:12Z; upload is the owner's
- [x] b01 carry-forward: elimination rule (each clue alone rules out a decoy), explanations clue-first, guess-the-year markers, FOUND (and FITS ALL 3) stamp, Tectonic labels, pipeline committed before packaging (`dirty` false)
- [x] Learn loop: collector status per platform checked on the Pi; Facebook reactions counted; posts export their questionId; `tools/retro_stats.py`; b01 retro "Performance" from real 24 h reads
- [x] Runway warning on Home and Studio › Overview (approve-by date = last scheduled day − 7)
- [x] `/video-batch` lessons (commit before packaging, fact-checker fallback, v2 fixes in `review.mjs` and the library scan), guide, security review, Pi sync

## 10. CHECKPOINT 1 answers (2026-10-11)

- **`_sources`: commit publicly.** Owner: "it is okay to commit them, this is not that serious." `library/_sources/**` (incl. future Whenabouts puzzles and the snapshot's game-repo files) is part of the public import. This is an explicit, recorded exception to the "no future game answers" public-safety rule; the check script allowlists `library/_sources/**` for that rule only. Supersedes §4.1 and the `_sources` exclusion in §4 step 3.
- **LICENSE: MIT for code + carve-out** (`CREDITS.md` for asset licences; brand/profile assets and channel names not licensed).
- **I3: move the platform/account IDs to Pi config.** Part of I-prep: the IDs (incl. `configure_paused.EXPECTED`, `metrics.py`, adapter constants) move to root-owned `/etc/scalar-social/config.json`, written on the Pi before the code ships; code fails closed if they are missing; tests cover the identity pin. This touches the live autopilot path, so it ships alone first, then the rest of I-prep.
- **Toolchains: reinstall** `studio/node_modules` (`npm ci`) and `studio/.venv` from the existing lockfile/requirements in Phase 1.
- Still open: owner approval of contract v2 (§5), repo strategy incl. I-prep (§4), Pi cutover plan (§7).

## 11. Open questions for CHECKPOINT 1 (as asked)

1. Audit: accept I3 (non-secret platform/account IDs stay in code) or move them to Pi config?
2. `_sources`: A (local + archive) or B (private sidecar repo)?
3. LICENSE: none, or MIT for code with an asset/brand carve-out?
4. Contract v2 as drafted, including one project per batch and the attribution rule (packager writes, validator enforces, Pi verifies)?
5. Repo strategy incl. the I-prep step and the import exclusion list?
6. Pi cutover plan; and the preconditions (publisher health first).
7. OK to reinstall `studio/node_modules` and `studio/.venv` from the existing lockfile/requirements?
8. Old StudioZero tracked Pixabay music and base videos: untrack going forward (history stays) — confirm.

## 12. Phase 1 log

- **Toolchains**: `studio/node_modules` reinstalled from the lockfile (`tsc --noEmit` green). The venv is recreated after the move (venvs hold absolute paths).
- **Pi config (no repo values)**: `/etc/scalar-social/config.json` gained `identities` (9 pins, all equal to the live channel settings; scope fingerprint unchanged; backup in `/var/backups/scalar-social/`). `/etc/scalar-social/ui.env` holds `SCALAR_UI_ORIGIN`. After 213dc9e the unit apply ran `ok`, the UI is healthy, and the publisher's failing-closed state is unchanged (2 uncertain jobs + Threads renewal; owner).
- **Private repo** (`scalargame-marketing-plan`): 2a97346, 213dc9e on main = GitHub = Pi. Publisher tests 453 green.
- **New repo** built in `~/Personal/code_projects/StudioZero-next` (clone of StudioZero): legacy-final b6e4962 → d82f37e retire → ac49364 engines/story → 38254f4 import → studio docs. The import leaves out the historical prompts with private paths and the six Gemini beds (local, ignored); root docs redacted (tailnet name, ssh key path, sudo note, links to removed records).
- **Accepted, for owner confirmation at CHECKPOINT 2**: the Pi's short LAN name/login user `scout` stays in historical notes (`docs/REBUILD_PLAN.md`) and one-off deploy scripts; tailnet names, IPs and IDs do not.
- **Safety check**: `tools/public_safety_check.py` (+ the private hash list) reports 0 findings for the whole tree; probes for each rule and a real ID from the private history are caught.
- **Verified in the new folder** (with the real local data): both finalized batches validate (one pre-existing `dirty_generator` warning recorded in them); `node studio/pipeline/check.mjs` reproduces `questionsHash 5ab19d44…` and `git diff --exit-code` is clean; publisher 453 + contract tests green; UI typecheck/lint/259 Vitest/check:static green; motion `tsc` green; the safety check passes on every commit that a push would publish (the two legacy commits only carry files already public at dc12780).
- **CHECKPOINT 2 answered** (owner): push + branch protection; push the game repo; "fix the Pi issue and start the transition now"; accept `scout` in historical notes.
- **Pushed**: StudioZero main a653c42 (+ tag `legacy-final`, branch protection); game repo cf46e1d (Vercel deploy success).
- **Pi issues fixed** (2026-10-11): YouTube job 64d0… resolved `--not-published` (no Buffer post, no YouTube upload after 10-06; it had held the YouTube queue since 10-10); Instagram comment 0550… resolved `--confirmed` (seen on the public reel; the API comments edge returns no own comments, so every daily first comment will stick: publisher fix pending, §13); today's reel 7a42… passes every receipt check and confirms on its own; Threads renewal fixed in 17894f6 (the refresh endpoint needs `access_token` as a query parameter) and renewed (expires 2026-12-10), failure marker cleared.
- **Cutover**: `migrate-origin.sh` dry run then real run 2026-10-11 23:03Z; independent checks green (origin StudioZero, partial+sparse, clean, ownership, UI health, timers, not paused, units-applied at HEAD). Rollback copy `/opt/scalar-social/repo.pre-studiozero-20261011T224347Z` kept until the deploy key moves.
- **Layout**: `studio/` → `engines/motion/` with the contract's ffprobe fallback path; regression byte-identical, both batches validate, Remotion still renders.

## 13. Owner follow-ups

All four Phase 1 follow-ups are done (2026-10-12; §14). Open owner decisions are listed at the end of §14.

## 14. Phase 2 log

- **Owner follow-ups (2026-10-12)**: the Pi's read-only key (`scalar-social-update@scout`) is attached to StudioZero only; on the Pi `ugit push --dry-run origin HEAD:refs/heads/readonly-probe` answers "marked as read only" and a queued update check is green (origin StudioZero, behind 0). `scalargame-marketing-plan` archived (private, read-only; history kept). Rollback copy `/opt/scalar-social/repo.pre-studiozero-20261011T224347Z` removed. `StudioZero-old-2026-10` and `scalargame-marketing-old-2026-10` deleted after checking that every file is in the backup, on GitHub (213dc9e, `legacy-final`) or newer in this repo. `~/CLAUDE.md` row applied. d983053: `bootstrap-git.sh` clones StudioZero; guide pages and `SELF_UPDATE.md` name it; the updater still accepts the old names.
- **Instagram first comments** (ea31a8e; verified: today's stuck comment `ceb17a17…` confirmed by itself at the 02:00Z tick with its permalink): a read-only diagnostic on the Pi (GET only, on a copy of the ledger) showed that with the Instagram Login token `GET /{media}/comments` returns no own comments, `GET /{comment-id}` answers 200 with an empty object for an existing comment (no field is readable) and 400 (code 100, subcode 33) for an unknown one, and the media's `comments_count` is correct. Reconcile now confirms a comment whose id came from this job's own create response when that object exists and the parent counts at least one comment; `publishedAt` is the dispatch time. Unknown, deleted or uncounted stays `uncertain`; other errors propagate; reconcile never posts; a lost create response (no id) still needs an exact own-account match in the list. 3 new tests.
- **Layout**: quiz kit → `engines/motion/src/projects/scalargame/`; two stills of `sample-props.json` byte-identical before and after; `check.mjs` reproduces `5ab19d44…` with a clean diff.
- **render.json** (`tools/RENDER_JSON.md`): engine → packager format with video/cover hashes, models, `costUsd`/`costEstimated`, per-asset `credits` (licence list from contract v2 §5.2 plus `unknown`), `disclosure`. Motion: music bed (CC0 artist and page, or the owner's Gemini track as licence `owner` with `aiKinds: [music]`), the style's OFL fonts, procedural SFX, Natural Earth (Scalar, Tectonic) or World Bank CC BY 4.0 (Continuum).
- **Packager**: `tools/package.mjs` reads `review/jobs/*/render.json`, checks each, calls the project module (`projects/scalargame/package.mjs`: the caption templates moved out of `batch.mjs`; site, campaign, hashtags from `project.json`, caption limits from `studio.json`), checks the delivered files' hashes, writes `batch.json`, runs the validator. `--dry` output equals the old script's (24 episodes; only `createdAt`/`dirty` differ).
- **Regression**: `node tools/package-regression.mjs` derives render.json from the finalized jobs into a temp copy, clones the media (APFS clone; the validator refuses symlinks and wants the folder named after the batch), re-packages with the finalized `createdAt`/`repoCommit`/`dirty`, validates (1 pre-existing `dirty_generator` warning each) and `git diff --no-index --exit-code` → both byte-identical.
- **Catalog**: `publisher/catalog.json` (projects, engines with templates + timings, styles, 96 beds (6 owner beds `retired`), story routes, default models, 11 video models, tiers; channels). Deterministic; the exporter refuses a project format its engine cannot render.
- **Story engine** (`engines/story`; details `engines/story/docs/HEADLESS.md`): venv python3.12 from `requirements.txt` (no new dependency; `google.api_core` became an optional import in `gemini_tts.py`). `python -m src.cli --headless --route recap|series …`. Smoke test `.venv/bin/python -m unittest discover -s tests -v`: 34 tests, 1 skipped (`RealRendererTest`: no ffmpeg here can run the recap renderer's filter graph; the Remotion-bundled ffmpeg lacks `setsar`, `fps`, `loop`, `asplit`, `aloop`, `sidechaincompress`, `ass`; the smoke run uses a test-only stand-in renderer), 1 expected failure (B3). Every key is `dummy-not-a-key`, `.env` and `output/settings.json` are not read (`STORY_SETTINGS_FILE`), sockets and DNS raise; recap stubs TMDB/Wikipedia/LLM/TTS/Pexels/Whisper; series copies the `Galactic_Garage` fixture to a temp dir and stubs only the provider network calls, so the real retry/fallback/budget/ledger code runs. Each run's `render.json` passes `node tools/render-json.mjs`.
- **Story render.json**: recap in `output/final/<safe_title>/` (new layout: mp4 + `cover.jpg` + `script.json` + `render.json`; the old dashboard's finals list no longer shows recaps), `episodeId` `originals-recap-<slug>[-<year>]`, models llm (or the Groq fallback)/tts/asr, credits Pexels (photographer, page), TMDB (with the notice), Wikipedia (article URL), and `unknown` for the stock fallback clips, the untracked music and the caption font; `costUsd` 0 with `costEstimated: true` (no LLM/TTS price tables yet; token usage recorded in `job.llmUsage`). Series per episode in `episodes/episode_N/`, models = the video models that actually made clips (from the ledger), `costUsd` = ledger estimate incl. billed failures, `realisticSynthetic` from the shot prompts (defaults to true unless clearly stylised).
- **Story bugs** (§3.5, appendix §2). Fixed: **B4** per-project `spend_ledger.json` (each billed attempt recorded at submit with the model that ran; `BudgetGuard` starts from the ledger; existing clips backfilled once; a corrupt ledger raises; Veo costed at 8 s); **B6** submit / wait / download split (submit retried only when the request provably never started; wait and download retried without re-submitting; fallback re-checks the budget; billed failures count); **B8** descriptions match prices. Partly: **B2** (`server.py`: Pause stops at the next step boundary, `/run` answers 409 while the old thread lives); **B10** (key sent as a header, error state reset). **Still open, blocking any paid run**: **B1** (dashboard recap review gate regenerates the script, paid); **B2** rest (a running `scene_generator` step renders every remaining scene); **B3** (no series TTS; mixed audio/no-audio clips concat to a silent final, mixed resolutions stream-copied); **B5** (settings reload; `FAL_KEY` not exported); **B7** rest; **B8** rest (Seedance endpoints unverified, fallback order not by price, `change_model` global); **B9**; LLM, image and TTS spend not in the ledger; a submit that times out after sending is neither retried nor counted (spend can be under-counted). Phase 3's studio agent replaces `server.py` (B1/B2/B5 there).

**Pi note:** the publisher still reports `ok: false` until about 22:45Z on 10-12 because the YouTube slot of 10-11 20:00Z expired (`missed_slot`) while the earlier uncertain YouTube job held the queue; it clears by itself (`missedLast24h`).

**Owner decisions (open):** target mix shares per project and an Originals monthly budget (both manifests say `target: null`, Originals `monthlyUsd: 0`, per-run approval); a full ffmpeg (with libass and the standard filters) for real recap renders (a system package, needs your OK).

## 15. Phase 3 log

- **Catalog + mode 1** (ca7f969): `GET /api/catalog` (ETag, 304, 512 KB cap; `ui_catalog.py`), `GAMES` from the catalog on both sides; prompt builder mode 1 (`promptBuilder.ts`: plan → brief → `/video-batch` hand-off or the Originals playbook; presets in `localStorage`; fixed `SAFETY_LINES`).
- **Studio tab** (dbfebad): sixth section; Make a batch moved to `#/studio/make` (old hashes redirect); per-project checklists.
- **Kit in the browser** (437170d): SFX and beds through `@remotion/media` `<Audio>`; CSS the web renderer cannot draw (repeating/radial gradients, masks, blend modes, inset shadows) redrawn as explicit-size SVG (`kit/paint.tsx`). Browser stills of all 8 formats match `remotion still` within 0.77/255 mean; `render.sh` output with the new kit within 0.19/255 of before (house look unchanged, ≤ 0.09 on the stills). **`render.sh` audio after the `<Audio>` switch is not bit-identical**: the mix differs at SFX attacks (−35.6 dB RMS difference; decoder differences, not resampling; tested with 48 kHz SFX). Video frames are byte-identical. Loudness and true peak still pass.
- **Pure cores** (1291a0b): `tools/package-core.mjs`, `tools/render-json-core.mjs`, `projects/scalargame/package-core.mjs`, `engines/motion/pipeline/render-json-core.mjs`, shared by Node and the browser (`@studio` alias); regression byte-identical.
- **Assets from the Pi** (686c53c): `publisher/motion-assets.json` (131 files, 72.7 MB; allowlist + sha256 = ETag), `/api/assets/motion/<version>/<path>` (immutable, Range, symlinks and size mismatches refused); the updater applies `publisher/deploy/sparse-paths` (adds `engines/motion/public`). Pi measurements: 131 files in 4.0 s at 8 parallel, UI peak RSS 35.7 MB (cap 96 MB), Range 206, revalidation 304; over the tailnet about 85 ms a request, a 1.2 MB chunk in 0.5 s.
- **Export** (9bb1ddb, 8407d65): Studio › Export opens a private job bundle (`web-jobs.mjs` → `review/web-jobs.json`, never committed), previews in the Player, exports with `renderMediaOnWeb` (H.264 3 Mb/s + AAC 192 kb/s), masters in the browser (BS.1770 gating, BS.1770-4 true peak, limiter to −1.5 dBTP for headroom), fixes the browser MP4 (AAC priming 2112 samples measured by cross-correlation → `elst`; last `stts` delta), checks like `render.mjs` plus sync, resumes from IndexedDB, writes `render.json` with `job.renderer: "web"`, packages with the shared cores and uploads through the normal flow. CSP gained `'wasm-unsafe-eval'`, `worker-src 'self' blob:`, `connect-src 'self' blob:`; Remotion's usage ping stays blocked (`licenseKey: 'free-license'`, the owner qualifies as an individual). All 8 formats exported on the Mac in Chrome (20–26 s an episode) pass browser QA and `qa_media`; the browser `batch.json` is byte-identical to the Mac packager's; the Pi validator passed and a Pi test instance imported 8 reviewable episodes. **Side by side `scalar-clues-901`** (browser vs `render.sh`): 5.0 MB vs 1.8 MB; frames 0.77 mean / 2.2 max difference; sync lag 0; −14 LUFS both; true peak −1.5…−1.9 dBTP vs −1.7 dBTP. Not yet run: Safari 26 and a phone (owner devices).
- **Proposal: how job inputs reach the device that renders** (owner decision; nothing built beyond A). (A, today) Claude writes `review/web-jobs.json` on the Mac; the owner opens it in Studio › Export on that device (or moves it by AirDrop/iCloud). Private, no Pi change, but the bundle must travel by hand. (B, recommended next) the Mac uploads the bundle to the Pi's private state (an authenticated `PUT` like the batch upload, size-capped, never in git, deleted when the batch is finalized); Studio › Export lists it on any device. Private and device-independent; adds one stdlib endpoint and a cleanup rule. (C) commit bundles or props to git so the Pi's checkout has them: simplest transport, but the repo is public and props name unposted answers, so only if the owner accepts publishing answers before they post (the `_sources` exception does not cover this).
- **Story worker + proxy** (07e4976): `engines/story/src/agent.py` (see §9 parity list; B1, B2, B5 fixed; paid runs off unless `STUDIO_AGENT_ALLOW_PAID=1`; 17 agent tests); `publisher/app/studio_proxy.py` + `scalar-social-studio-proxy.service` (allowlist, one pinned tailnet worker, caps, "Worker offline"); Story jobs pages; `server.py` and `static/` retired. Live check through UI → proxy → agent (paid off) on desktop and mobile (`e2e/story.spec.ts`, opt-in). Pi: proxy active, socket `srw-rw---- scalar-social`, other users refused, UI without a session 401, **Worker offline** 503 in 3.7 ms, proxy RSS 12–19 MB (cap 48 MB); locally proxy → agent about 2 ms a request, a 6.6 MB clip in 12 ms, Range 206.
- **Security review** (`plan/PHASE3_SECURITY_REVIEW.md`; independent reviewer, two rounds): one medium fixed (F1: the worker chose the Content-Type of responses served from the Pi's origin, so worker files could run script in the UI; now fixed types by suffix, downloads otherwise, a sandbox CSP on every studio response), lows fixed (unreachable non-ASCII ids, model-written ids in file paths, laptop paths and job state files served, unquoted ssh arguments, auth after body parsing, case-insensitive private names, absurd Content-Lengths); also fixed: `project.json` is now written atomically (a poll during a run could read a half-written file; found as a 1-in-15 flaky agent test). Accepted with reasons: the budget cap is not a second gate against a stolen session (the laptop's `STUDIO_AGENT_ALLOW_PAID` is), the Pi trusts browser loudness/black-frame QA, no overall proxy deadline.
- **Mode 2** (d46d658): Studio › New format, style or project → a Claude Code prompt for the template + one pilot (browser render limits, the pilot's job bundle for the Player, ask before pushing; story pilots $0 first, paid only after a confirmed estimate; a new project's budget and mix left to the owner).
- **Tests at the end of Phase 3:** publisher 487, contract, story 49 (1 skip, 1 expected failure), UI Vitest 337 + typecheck + lint, motion `tsc`, `check.mjs` → `5ab19d44…`, packager regression byte-identical, both finalized batches valid, `check:static` clean, safety check 0. e2e: all pass except `smoke.spec.ts` (both projects), which still asserts the typed schedule-approval phrase retired on 2026-10-09; changing that assertion was blocked as a security-test edit, so it waits for the owner.
- **Pi note:** the publisher and monitor units exit 2 (report `ok: false`) since 2026-10-11 22:45Z for the missed YouTube slot noted in §14; it clears by itself after 24 h. Jobs keep flowing.

**Owner items:** set up the laptop worker (Tailscale Serve on the laptop + `scripts/agent-token.py --send-to-pi`, `engines/story/docs/HEADLESS.md`); try an export in Safari 26 and on a phone; OK to update the smoke e2e assertion; decide whether job inputs reach the Pi through git (commit `web-jobs`/props publicly, which names unposted answers) or stay private bundles opened on the device (today); enabling paid story runs after B3 and the rest are fixed; the open decisions (mix targets, Originals budget, full ffmpeg).

## 16. Phase 4 log

- **Owner answers (2026-10-12)**: add `render.renderer` to v2 (`render.sh`, `web` or null); switch Scalargame to v2 in Phase 4; update the smoke e2e's retired typed-phrase assertion.
- **Validator v2** (615d5cc): `validate_document` dispatches on `schemaVersion`; the v1 code is unchanged apart from `link_for` (v2 branch first) and a lazy `expand` (no link computed when the text has no `{link}`). Project modules are loaded by file path from `contract/projects/` (registered = the files there; a name not in that list is refused before any import); namespaces must not collide across modules. Core v2 rules as §5.1–5.2 plus `render.renderer`; `asr` is an allowed model role (render.json already records it). Pi-side helpers: `episode_view` (the §5.4 normalization for views and policies), `project_of`, `content_id`, `required_attributions` / `missing_attributions`. The finalized batches' documents validate in `contract/tests/test_contract_v2.py` (skipped on the Pi, whose sparse checkout has no `library/`; the first ship failed the updater's staged contract tests for that reason, so the updater refused it and the Pi stayed on the old commit; fixed in 6908515).
- **Packager v2** (529b2e9): `tools/package-core.mjs` writes v1 or v2 (`--schema` overrides project.json; the regression passes the finalized batch's version). v2 episodes copy models, cost, credits, disclosure and `job.renderer`; `renderSha256` = sha256 of the render.json file (motion writes `renderJsonText`, the browser hashes the same text). The Scalargame dry run of the 2026-10 set (24 episodes) validates as v2; Continuum captions carry "World Bank Open Data (CC BY 4.0)" on every platform, X included. `projects/originals/package-core.mjs` builds v2 episodes from story render.json + `review/originals.json` (the reviewer's checks); a platform whose limit cannot hold the caption with its attribution gets no caption (does not post) and a warning. With today's story attribution texts (TMDB ≈ 130 characters, Wikipedia ≈ 130) a recap posts on Instagram, Facebook, TikTok, Threads and YouTube, not on X or Bluesky: Phase 5 decides shorter attribution wording or first-comment placement.
- **Pi import** (d431b96): no schema change; `episodes.question_id` = contentId, `episodes.game` = scheduling group (v1 game; Scalargame v2 `projectData.game`; else the project id). Schedule records keep their v1 shape, so library hashes and v1 drafts are unchanged (checked on the Pi: old and new code produce draft `3a474365…` from the live library, 67 posts). The generator verifies that each v2 episode's required attributions post on each platform (caption, or a first comment the draft will post) and blocks edits that drop them.
- **Mix** (79f5541): ordering `project-mix` + `mix` input (shares 0–1 per project); each project's queue in game round-robin order, interleaved by smooth weighted round-robin (ties by name); share 0 or no share = left out, with a reason. `autopilot.catalog_mix`: null while every project's target is null (today: verified on the Pi, inputs identical); otherwise a project without a target gets 0. The UI's recommended plan mirrors it.
- **AI labels** (f3a33d0), verified 2026-10-12: Instagram `is_ai_generated` on the media container (Instagram Platform changelog, 2026-06-22); Buffer `isAiGenerated` on `YoutubePostMetadataInput`, `TikTokPostMetadataInput` and `TwitterPostMetadataInput` (Buffer API changelog, 2026-06-09); Facebook Reels (`video_reels`), Threads and Bluesky have no field. YouTube follows `realisticSynthetic` (its label is for realistic content); the others follow `aiGenerated`. Not yet exercised live: the first AI-labelled post is the live test (owner OK). Buffer X thread metadata now merges with `twitter.isAiGenerated`.
- **UI** (ea8808d): `LibraryEpisode` gains schemaVersion, project, engine, route, renderer, models, costUsd, credits, disclosure, tags; `readEpisode` reads v2 `projectData`; Learn's `FunnelGroups`; `EpisodeFunnel.labels` from `ui_library.content_labels`; per-project runway (`Runway.lastDayByGroup`); guide pages studio, glossary, schedule, review, next-batch. The journey e2e also had a stale activation label (changed 2026-10-09), fixed.
- **End to end**: a scratch v2 batch (`library/_dev/2026-10-v2scratch`, three real 2026-10-b01 renders renamed to `*-901…903`, owner-made music, so AI-declared) validates with ffprobe; with the v1 `2026-10-pilots` in one throwaway state: import, upload, approve 7, recommended draft 49 posts (v2 episodes scheduled), project-mix draft identical in fill, labels applied on Instagram/TikTok/X, not-needed on YouTube, not-supported on Facebook/Threads/Bluesky, v1 payloads without a disclosure. Same run on the Pi: 8.4 s, peak RSS 26.6 MB.
- **Pi**: on ea8808d; UI RSS ≈ 34 MB (cap 96 MB), proxy ≈ 9 MB (cap 48 MB); not paused; next autopilot 17:15 ET. The publisher exits 2 (`ok: false`) for the missed YouTube slot of 10-11 (clears by 22:45Z) and a Bluesky post of 14:30Z waiting for remote confirmation (`remote_confirmation_pending`, dispatched before the first Phase 4 update from the already-approved v1 manifest; re-checked hourly; owner check if it lasts a day).
- **Security review** (independent reviewer, read-only, with local fuzzing of the validator; nothing high): fixed: (M) an edit or removal could drop a required attribution that only a first comment carried (the generator now re-checks every new post against what actually goes out: its text, X thread items and the first-comment jobs left under it); (M, part) link targets are now shown on the review screen (Made with › Link) and URLs are strict (printable ASCII, IDN in xn-- form, parse round trip, valid port; credentials refused) — the reviewer's other suggestion, a host allowlist for Originals links, is a rule beyond §5 and is left to the owner (Originals links are optional and none exist yet); (L) wrong-kind values (lists where text belongs) are refused instead of raising, in the validator and around the import; (L) control characters in URLs; (L) catalog mix targets the generator would refuse fall back to the round-robin so the autopilot never stops on them; (L) attribution text capped at 500 characters and long texts truncated in messages; (L) `namespace_owners` memoized; (info) `schemaVersion` must be the integer 2. Checked clean: project-module loading (exact names only), nothing from batch.json reaches Graph or Buffer payload keys, v1 path unchanged, parameterized SQL, no HTML injection in the UI (credits and disclosure render as text; links go through `httpsUrl`), bounded regexes, `project_mix` terminates.
- **Tests at the end of Phase 4**: contract 63, publisher 515, story 49 (1 skip, 1 expected failure), tools 6, UI Vitest 345 + typecheck + lint, e2e 8 (smoke, keyboard, guide, stats, journey; mobile and desktop) on a fixture, motion `tsc`, `check.mjs` → `5ab19d44…`, regression byte-identical, `check:static` clean, safety check 0.

## 17. Phase 5 log

- **Contract-ready story renders** (7bb6d07). `render_json.conform_for_contract` re-muxes or re-encodes only what is off (AAC 48 kHz stereo, H.264 yuv420p, fast start, ≤ 24 MB) before probing; the recap renderer now writes 48 kHz, fast start and a 2.4 Mb/s cap (it wrote 44.1 kHz without fast start: every recap would have failed the validator). Licences: recap music is a CC0 track from `engines/motion/music/catalog.json` (artist, page, sha256 checked; local sources only) or none (`RECAP_MUSIC`); `assets/music` and `assets/basevideos` are never used (a scene with no Pexels match takes generic Pexels footage, else fails); captions use Fraunces Black (OFL, `engines/story/fonts/`, WOFF because Homebrew's FreeType has no WOFF2) through libass `fontsdir`. Engine episode ids stay work ids; `tools/stage-story.mjs` assigns `originals-<format>-<nnn>` (next number unused anywhere in `library/`, `--number` for scratch), copies media into the batch, keeps `job.workId`, writes a `review/originals.json` skeleton with every check false, refuses unknown licences and finalized batches, and is idempotent.
- **Spend**: `src/pricing.py` prices every Gemini/Groq text, image and TTS call (Gemini pricing page and Groq list prices, checked 2026-10-12; an unknown model is charged at the table's highest rate) into the project's `spend_ledger.json` (`kind` llm/image/tts; video entries unchanged). The series pipeline charges per episode (project-level work shared equally across episodes in `costUsd`); a recap charges its script and narration (worker: the job folder; CLI: the recap's temp folder). The ledger re-reads the file under a per-file lock before every write, so the meter and the scene generator never drop each other's entries. A submit that fails after it may have reached the provider (timeout, 5xx, dropped connection) is recorded `uncertain`, counted, never retried; a 4xx rejection is not counted.
- **Paid-run bugs** (7bb6d07). B3: the editor normalises every clip (1080x1920 centre crop, 30 fps, H.264, AAC 48 kHz stereo; a silent track where a clip has none) and joins identical segments; series ask for native audio where the model has it (`SERIES_NATIVE_AUDIO`), so a Veo clip among silent fal clips keeps its audio (the smoke test's expected failure now passes). B8: every video model checked against fal.ai's OpenAPI schemas and model pages and the Gemini pricing page (2026-10-12). Findings fixed: Seedance 2.0 Fast/Standard cost $0.2419/$0.3034 a second at 720p, not the assumed $0.052 (about 5× under-estimated); `seedance-1.5-pro-fast`'s endpoint did not exist (now `seedance-1.5-pro`, real endpoint; the old id still resolves); Wan 2.5's endpoint did not exist (now `fal-ai/wan-25-preview/…`); Kling 3.0 image-to-video takes `start_image_url`; Seedance reference-to-video takes `image_urls`; audio is `generate_audio` (the client sent `enable_audio`, which no model reads); text-to-video defaulted to 16:9 (now 9:16 where the schema takes `aspect_ratio`); Sora 2 Pro's endpoints could not be found, so it is unverified and never called, listed or offered. Each model has a `clip_seconds` (5 s fal, 8 s Veo); the tier fallback is the current model, then the others cheapest first (registry `fallbackOrder`, kept sorted by a test). B9: dead Vertex/Drive/Sheets/iCloud config removed; Veo requests 35 s apart. B10: stale fallback errors reset per call. `PipelineStatus` moved to `src/status.py`. The worker refuses unverified models and prices every line of its estimate (`src/estimates.py`, also `--estimate` on the CLI).
- **Playbook** (a7208cf): `.claude/skills/originals/` (SKILL.md, review-checklist.md, contact_sheet.py), `.claude/agents/originals-fact-checker.md`, `library/_templates/ORIGINALS_BRIEF.md`. Rehearsal at $0 on a real render: the local Galactic Garage project (all paid steps from April 2026) re-edited with the network blocked; this found that an editor-only re-run on a project older than the ledger wrote video model `unknown` at $0, now backfilled (veo-3.1-lite, $2.00). Staged, checked (contact sheet), packaged and validated as `library/_dev/2026-10-o901` (v2, ignored by git).
- **Studio** (6cb10e7): Make a batch › Originals copies `/originals brief <batchId>` (`YYYY-MM-oNN`), lists models from the catalog, a verified video model choice for animated shorts, the platforms that post, AI labels and the mix; checklist = the playbook's checkpoints; guide pages updated. `.claude/launch.json` `publisher-ui-dev` runs the UI on the fixture state from `publisher/tests/ui_fixture_state.py` (`library/_dev/ui-fixture`); the fixture's `work/2026-10-second` must be finalized before the journey e2e.
- **Pi throwaway run** (2026-10-12, `/tmp` only, removed after): `2026-10-pilots` (v1) and `2026-10-o901` (v2) imported with the Pi's ffprobe and frame grab, approved, drafted: game round-robin (no targets) left the Originals episode out of a 4-day draft behind the Scalargame videos; project mix (75/25 example) placed it second; labels: Instagram, TikTok, X applied; YouTube not needed (stylised); Facebook, Threads, Bluesky not supported. 5.8 s, peak RSS 44 MB. Pi on 6cb10e7, UI and proxy active, not paused, autopilot next 17:15 ET.
- **Pi note**: the publisher exits 2 for one Facebook post of 2026-10-12 16:15Z waiting for remote confirmation (`remote_confirmation_pending`, re-checked hourly) and one missed slot in the last 24 h; the Bluesky post noted in §16 is confirmed. Owner's to resolve if it lasts (never re-post).
- **Security review** (independent reviewer, read-only, on e8048b9..6cb10e7; nothing high). Fixed: (M) `fal_client.submit` retries internally up to 10 times on timeouts, dropped connections and 408/409/429, so one scene could queue and bill several jobs while the ledger counted one: the submit now runs with the SDK's `MAX_ATTEMPTS` set to 1 (fails closed if the SDK changes), tested through the real SDK with a transport that times out after sending (exactly one POST); (L) settings could change mid-run (models, budget) after the estimate was confirmed: PUT settings answers 409 while a run is in progress; (L) a submit failing with an unexplained error was counted as never sent: only a refused connection, missing credentials or a 4xx other than 408 now count as not started; (L) `tools/stage-story.mjs` copied `job.script` without containment: video, cover and script must be relative paths whose real path stays in the render folder (symlinks refused); (L) `--number` validated (1–9999); (info) the ledger also takes a file lock (CLI and worker on one project) and updates by entry id; the random-idea call is never charged to a running project; the Originals fact-checker has no Write tool any more (it returns the JSON; the playbook saves it), so a prompt injection in a fetched page cannot make it write files. Accepted: the Scalargame `fact-checker` agent keeps its Write tool (same pattern; owner may want the same change); the global spend meter is per process (one run at a time per process).
- **Tests at the end of Phase 5**: story 79 (1 skip: the real recap renderer needs a full ffmpeg), tools 11, contract 63, publisher 515, UI Vitest 346 + typecheck + lint, e2e 8 (story spec opt-in, skipped), motion `tsc`, `check.mjs` → `5ab19d44…`, packager regression byte-identical, `check:static` clean, safety check 0.

## 18. Phase 6 log

- **State at start** (2026-10-12): local = GitHub = Pi at dbe43ca; 24 Scalargame episodes approved, scheduled to 2026-10-30; no open feedback or batch notes on the Pi. The Facebook and Instagram jobs uncertain at handoff were confirmed; YouTube failed three days running (10-10 `owner_verified_absent`, 10-11 missed slot, 10-12 `remote_confirmation_pending`), owner's to resolve.
- **Checkpoint 0** (owner): 32 main + 8 spares (4 per format, 4/3/1 per game, to about 2026-12-01), pilots inside the batch, Whenabouts freshness waived. Elimination: two decoys over three clues means one clue always removes nobody in order, so the rule is "each clue alone rules out a decoy" (`CONFIG.rules.everyClueRulesOutADecoy`, opt-in; the 2026-10 regression unchanged).
- **Fact-check** (independent, three rounds): Morocco as a decoy depends on Western Sahara (replaced by Equatorial Guinea and Algeria); Sweden's World Bank area includes ~81,000 km² of sea (Germany vs Paraguay instead); iPhone/YouTube dates imprecise (dropped; its ID retired); Google/Titanic and Eswatini reworded. The `fact-checker` agent type did not load because the session started outside the repo; a general-purpose agent followed its definition (now in the skill).
- **Templates** (pilots approved at Checkpoint 2): guess-the-year pans toward the answer only as far as keeps all three choices on screen (zoom 1.35 → 1.2); the stamped clue clears fully under FOUND (clue 3) and, found at Checkpoint 3, under FITS ALL 3 (clue 1).
- **Render and review**: Belgium failed QA at −0.8 dBTP after AAC; `render.sh` masters now stop at −1.5 dBTP (QA bar −1 unchanged; `master_audio.py` is not in the kit hash). Full-resolution stills found two population head-to-heads whose hook + question overlap the brand label and Colombia's stacked labels; the owner swapped them (Peru/Australia, Sweden/Benin, Guatemala). The first v2 Scalargame batch exposed v1-only reads in `review.mjs` and `libraryEpisodes()` (repeat checks and the calm-bed rotation); both fixed. Final: 32 validated, validator 0 warnings, `dirty` false (4322362), finalized 2026-10-13T02:12:22Z.
- **Learn loop** (Pi, read-only check): the collector reads Instagram, Threads, Facebook, Bluesky, YouTube, TikTok and X (`last-run.json` all `ok`). Gaps: Facebook Reels report reactions only as a breakdown, so engagements were never set (fixed, 69bfba2); YouTube has one read because its posts failed; no A–D answers anywhere yet (no audience replies; Instagram's one comment per post is our own first comment); X at 0 impressions at 24 h through Buffer; one Facebook post reports a 50-minute average watch on 1 play (platform data, not changed). The feedback export now carries each post's questionId (7b48f46) and `tools/retro_stats.py` groups it by platform, game/format and matched checkpoint. b01's first numbers (24 h, two episodes): Instagram ~180 views, TikTok 93–306, Threads/X/Facebook ≈ 0; average watch 2.5–5 s of 20–24 s.
- **Runway** (69bfba2): the dashboard standing gains `contentThrough` and `nextBatchBy` (last scheduled day − autopilot.RUNWAY_DAYS); Home switches to "Make the next batch" 14 days before the end with both dates; Studio › Overview shows them per project. Verified in a browser on a fixture with a schedule (375 px, no overflow).
- **Security review** (independent, read-only, nothing above low): a damaged manifest made the dashboard 500 instead of hiding the dates (fixed: fallback to null, 04f6440); an unparsable day could break Studio › Overview (guarded). Info: dates are server-made ISO strings rendered as text; no new endpoints, permissions or writes.
- **Tests at the end of Phase 6**: publisher 516 (1 skip), contract OK, tools 11, story 79, UI Vitest 347 + typecheck + lint, e2e 8 passed / 6 skipped (installed Chrome; Playwright's bundled browser is not downloaded), motion `tsc`, `check.mjs` → `5ab19d44…`, packager regression byte-identical (pilots, b01), all three 2026-10 batches validate, `check:static` clean, safety check 0. Pi on the pushed main; UI ≈ 34 MB of 96 MB; not paused; the publisher still exits 2 for the uncertain YouTube job (owner).

## After Phase 5

Phase 5 was the last planned phase. What is left is owner decisions, deferred work and watching.

**Owner direction (2026-10-12):** Scalargame marketing videos are the main work. No Originals video is generated until the owner asks; the Originals pipeline stays wired up and tested at $0 (`library/_briefs/2026-10-o01.md` is on hold). ffmpeg 9.0.2 with libass now runs on the Mac (rebuilt from the `homebrew-ffmpeg/ffmpeg` tap formula the owner trusted). When Originals resume: Gemini AI Studio credits were depleted on 2026-10-12, and the Groq fallback model `llama-3.3-70b-versatile` is no longer available to the key (candidate: `openai/gpt-oss-120b`).

**Owner decisions (open)**
- The first Originals batch (on hold): `library/_briefs/2026-10-o01.md` (two recaps at about $0.02 each and the existing animated short), each paid run separately.
- Mix targets for both projects (`projects/*/project.json` `mix.target`): without them Originals post only after the whole Scalargame backlog; once any project has one, a project without one is not scheduled.
- Originals budget (`budget.monthlyUsd`, today $0 with per-run approval).
- Recap attribution wording (shorter texts would let recaps post on X and Bluesky) and CC BY-SA ShareAlike for narration adapted from Wikipedia (brief questions 4–5).
- A host allowlist for Originals links (Phase 4 security review; contract change), when the first Originals link is planned.
- Laptop worker set-up (Tailscale Serve + `scripts/agent-token.py --send-to-pi`); whether job inputs travel through the Pi (§15 proposal B); Safari 26 and phone export checks.

**Deferred / known debt**
- The real recap renderer now runs in the $0 suite (ffmpeg 9.0.2 with libass); it has not yet rendered real footage.
- Recap caption style: `PlayResX/Y` are landscape (1920x1080) on a portrait video; check the first real recap's captions in the contact sheet.
- Series have no narration step (the B3 policy is native audio or silence); a TTS narrator for series is a feature, not a fix.
- Old projects' LLM and image spend before 2026-10-12 is not in their ledgers (video is backfilled).
- Prices change: `src/pricing.py` and `registry.json` record their check date; re-verify before a large run. Sora 2 Pro stays unavailable until its fal.ai endpoints are confirmed.
- Pi-side loudness/black-frame checks of browser uploads (Phase 3 F7) and an overall proxy deadline (F8) stay accepted. The Scalargame `fact-checker` agent still has a Write tool (the Originals one no longer does).

**What to watch**
- Autopilot runs (05:15 and 17:15 Pi time): refills, activation, the publisher's `ok` flag.
- AI labels on the first live AI-labelled posts (Instagram `is_ai_generated`, Buffer `isAiGenerated` for TikTok and X): owner OK first, then watch the job and the public post.
- Spend: each Originals render.json `costUsd` and `job.costByKind` against its estimate and the monthly budget.
- The mix once targets are set (Studio › Overview runway per project).
- Pi memory: UI ≈ 35–45 MB of 96 MB, proxy ≈ 10–20 MB of 48 MB; the Pi Zero 2 W has about 250 MB available.

## Next

- **Owner**: upload `library/2026-10-b02/` on the Pi (Library → Add batch → Upload batch), add the brief and retro as batch notes, approve the episodes; do it before 2026-10-23 so the autopilot's refill finds them. Resolve the YouTube posts (three days not posted).
- **Watch**: the autopilot refill around 2026-10-24 (Activity › "Autopilot (schedule refill)"); the next batch is due by about 2026-11-24 (Home shows the date).
- **Learn**: once b01/b02 posts have 7-day reads, export feedback.json and run `tools/retro_stats.py` for the b01/b02 retros; viewers leave after 2.5–5 s, so the next brief may test an earlier hook or a shorter thinking window (owner decision).
- **Debt**: the head-to-head header holds three lines (hook + question): a template fix with a pilot, or keep choosing one-line questions; the Scalargame `fact-checker` agent still has a Write tool.

