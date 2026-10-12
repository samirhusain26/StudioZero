# StudioZero studio plan (running record)

Status: **Phase 2 done** (2026-10-12): owner follow-ups closed; manifests, render.json from both engines, shared packager (byte-identical regression), catalog, story $0 smoke path, Instagram first comments auto-confirm. Next: **Phase 3** (unified UI), prompt `docs/prompts/PHASE3_SESSION.md`. See §9, §14.

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

### Phase 3 — Studio tab, agent, proxy, prompt builder · Phase 4 — contract v2 + publisher · Phase 5 — Originals back online
As in the brief; not started. Session prompt for Phase 3: `docs/prompts/PHASE3_SESSION.md`.

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
