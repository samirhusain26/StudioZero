# End-to-end publishing pipeline and Pi management UI — plan

Status: plan locked with owner, 6 October 2026. **Built and tested 7 October 2026; installed (paused) by the owner 7 October 21:22 EDT** — see [PI_UI.md](PI_UI.md) for the operator guide and "Implementation status" at the end of this file. Installation awaits owner approval. Supersedes the deferral in [PI_UI_BACKLOG.md](PI_UI_BACKLOG.md). Creative generation decisions stay in scalargame `docs/growth/VIDEO_GENERATION_PIPELINE.md` (C01–C18, D01–D24); this plan covers the contract between that pipeline and the Pi, and the Pi's library, scheduling, approval, publishing and monitoring.

Nothing here enables publishing. Global pause, disabled channels and the disabled `scalar-social.timer` remain until a separate explicit activation.

## Flow

```
Mac (scalargame/marketing)                 Pi (scout, tailnet only)
render batch (Remotion) ─┐
QA + batch.json ─────────┤ library/<batchId>/ + finalize → READY_FOR_UPLOAD
                         └──── manual browser upload ────► import + verify hashes/contract
                                                           owner review & content approval (approval of record)
                                                           schedule generator → draft preview
                                                           owner approves draft → Pages deploy + public hash check
                                                           → approved manifest (bound by hash in config.approval)
                                                           [separate sudo activation: channels + timer]
                                                           runner tick --manifest → adapters → receipts in ledger
```

## Locked decisions (6 October 2026)

| # | Decision |
|---|---|
| L1 | An upload is a finished, self-contained video. It may link to a question/episode ID; linked videos get prefilled captions and share that ID's duplicate history. All captions are editable and frozen at approval. |
| L2 | The Pi UI is the single content approval of record (reviewer, time, file hashes, caption hashes). Mac review steps (question pack, pilots, QA) produce `qa-passed`, never `approved`. |
| L3 | The UI may: upload/import, approve content, approve a schedule, cancel/edit undispatched jobs, pause. Resume, channel enabling and timer enabling stay an owner-run sudo command that the UI displays with its readiness checklist. |
| L4 | A schedule approval is a finite batch: an exact closed list of jobs. Publishing stops when it is consumed. The rolling `--catalog` `BatchPreparer` is not used for UI schedules. |
| L5 | Validation uses per-platform limits; hard requirements are H.264, AAC or silent, 9:16, ≤ 24 MB (Cloudflare Pages). No transcoding or rendering on the Pi. |
| L6 | Access mirrors Finalyst: loopback bind, existing tailnet-only Tailscale Serve, mandatory passcode as Bearer token on every `/api/*`, custom CSRF header, per-client backoff, open `/api/health`. |
| L7 | Self-contained videos only. Chained assembly stays in the code, unused by UI schedules. |
| L8 | Per-platform posting days/times, per-account minimum spacing, optional stagger between platforms for the same video. |
| L9 | Media is deployed to Pages at schedule approval; approval binds the public URL + hash. |
| L10 | Demo runs on the Pi against a staging copy of state; no Pages deploy, no live config/ledger change. |
| L11 | An upload can be deleted only if it was never in an approved manifest; afterwards it is read-only and retained. |
| L12 | Mac→Pi transfer: upload `batch.json` plus its `videos/` and `covers/` files from the standard library folder in the UI, one request per file (revised 6 October from a single `.tar`). Single videos can also be uploaded from the phone with hand-entered metadata. |
| L13 | This build: the batch contract validator and the complete Pi side. Creative templates/renders (pilots, 24-video batch) are a later phase under VIDEO_GENERATION_PIPELINE.md. |
| L14 | Polls: choices in every caption, plus native/companion interactive posts where a verified route exists, falling back to an own first comment/reply. Details in [Polls and comments](#polls-and-comments). |

Not decided here, and not invented by the UI: posting cadence, launch scope, recurring activation. The schedule form starts empty and every generated draft requires explicit approval.

## Batch contract (Mac → Pi)

Specified in [BATCH_CONTRACT.md](../../contract/BATCH_CONTRACT.md): the standard folder `marketing/library/<batchId>/` (`batch.json`, `videos/`, `covers/`, `review/`, `READY_FOR_UPLOAD`), every `batch.json` field, the merge rules for adding to an existing library, and the validation rules. This build implements its validator `contract/library_contract.py` (stdlib Python, shared by Mac and Pi) first, so the generation work can validate against it.

## Pi components

Everything lives in this repo (`scalargame/marketing`); the Pi runtime stays stdlib Python + existing ffmpeg/ffprobe. No new Python dependencies.

| Component | Path | Runs as |
|---|---|---|
| UI backend | `publisher/app/ui_server.py` (+ `ui_*.py` modules): `ThreadingHTTPServer` on `127.0.0.1:8765` | `scalar-social`, no credentials except `UI_PASSCODE` |
| Frontend | `publisher/ui/` React 19 + Vite + strict TypeScript, built on the Mac; compiled `dist/` installed to `/opt/scalar-social/ui` | static files served by the backend |
| Approval applier | `scalar-social-approve.path` → `scalar-social-approve.service` | `scalar-social` with `CLOUDFLARE_API_TOKEN`; `ExecStartPost=+` root step writes only approval fields |
| Publisher | existing `runner.py` / `monitored.py` / adapters | unchanged user and credentials |

Port 8765 is what Tailscale Serve already proxies (`https://<pi>.<tailnet>.ts.net`, tailnet only; old Scout target is dead), so no Tailscale change is needed. No LAN listener, no Funnel.

### Canonical state (no parallel copies)

- Posting history, queue, receipts, errors: the existing `ledger.sqlite3` `jobs`/`events` tables. The UI reads it read-only except for cancel/edit of undispatched jobs, which take the existing `runner.lock` (non-blocking; "publisher busy" on contention).
- Library: `/var/lib/scalar-social/library/` — `objects/<sha256>.mp4`, `covers/<sha256>.jpg`, `index.sqlite3` (videos, metadata revisions, content approvals, schedule drafts). Original filenames are metadata only. Existing Pi media under `site/` is registered by hash in place, not copied.
- Approved manifests: `/var/lib/scalar-social/manifests/<sha256>.json`; `approved.json` points at the current one. The publisher reads it via `--manifest`.
- Approval binding: `config.approval` in `/etc/scalar-social/config.json` (existing fields). The UI never writes `/etc`.

### Upload and import

- Streaming request bodies in 64 KiB chunks, hashing while writing to `library/.incoming/<random>.part`; `Content-Length` required; per-file caps 24 MB video, 2 MB cover, 1 MB `batch.json`; refuse when free space < size + 2 GB.
- `batch.json` first; then each video/cover is its own upload, matched by sha256 to an expected file. Unexpected files, names outside `videos/<episodeId>.mp4` / `covers/<episodeId>.jpg`, `..` and absolute paths are rejected. Merge rules follow BATCH_CONTRACT.md.
- Interruption: partial files are never registered; `.part` files older than 6 hours and all `.part` files at startup are removed.
- Per video: ffprobe → `check_media`-style validation against a per-platform limits table (sourced and dated in `PLATFORM_MATRIX.md`); platforms a video fails are disabled for it, with the reason shown. Cover comes from the batch; for phone uploads one frame is extracted with ffmpeg (single-frame grab, not rendering).
- Duplicates: same sha256 → existing record reused, no new bytes; same `questionId` with a new hash → flagged as a variant sharing the reuse group; ledger history (including `previousAccountIds`) shows where that question already posted.
- Nothing is approved on import. Owner content/rights approval is per video (or "approve all shown") and records reviewer, time, file hash, metadata hash.

### Schedule generator (deterministic, preview only)

Inputs, all explicit: timezone (shown, `America/New_York` is not assumed), date range, per platform: include?, weekdays, times, max posts/day; minimum gap per account; cross-platform stagger; content ordering rule (default: game round-robin `scalar → continuum → whenabouts → tectonic`, interleaved difficulty).

Rules: only approved, eligible videos; one post per `questionId` per account ever (D22) including history under previous account IDs; respect `notBefore`/`reviewBy`/`expiresAt`; per-platform media eligibility; provider limits (Facebook 30 own finishes/day, Threads/Instagram API quotas, Buffer 200/day local cap, Pages 120 deployments/31 days); blocked platforms (TikTok) excluded with the reason; nonexistent spring-forward times are skipped and flagged, ambiguous fall-back times use the first occurrence and are flagged (same rule as `runner.slots`). Exhaustion is reported ("18 of 24 requested slots fillable").

Same inputs + same library/ledger state → byte-identical draft. Drafts live in the library index, never in the ledger. The preview shows, per job: local time (with zone abbreviation) and UTC, platform/account, video (cover, hash), exact caption/title/poll/comment, and warnings. The owner can edit individual entries or regenerate; any edit produces a new draft hash.

### Approval and binding

1. Owner approves a draft in the UI (typed confirmation). Backend writes a request file with the draft hash.
2. `scalar-social-approve.service` re-validates the draft against the library and ledger, deploys referenced media to Pages (one deployment; existing files retained), verifies every public URL by hash, then writes `manifests/<sha256>.json` with the exact job payloads and the intended channel scope hash.
3. Its root `ExecStartPost=+` step sets `approval.manifestSha256` and `approval.approvedAt` only. It never unpauses, enables channels or timers.
4. Activation (owner sudo command shown in the UI): shows the readiness checklist, enables exactly the channels named in the manifest scope, checks `fingerprint(config)` equals the manifest's scope hash, sets `scopeHash` and the verified flags only if the evidence files exist, removes `PAUSED`, enables the timer, then prints `systemctl list-timers` proof.

Publisher change: `scalar-social.service` uses `--manifest /var/lib/scalar-social/manifests/approved.json` instead of `--catalog`. With no approved manifest it fails closed. Manifest jobs carry final payloads, so `run_jobs` runs without `prepare`.

### Edit, cancel, history

- Dispatched records (`dispatched_at` set or status ≠ `ready`) are immutable.
- Cancel/edit of an undispatched job produces a new manifest version that must be re-approved; until then the old approval stands. Removing a never-dispatched `ready` row is done by the applier under `runner.lock` and logged as a `cancelled` event with the full prior row (the `UNIQUE(platform, account, episode)` constraint makes a tombstone row unusable for rescheduling).
- `uncertain`/`accepted`/`dispatching` jobs have no "post again". The UI shows the reconciliation state, last check, next check, and the documented owner actions (check the platform profile; mark resolved with evidence through a sudo-gated command). Absence from a feed is never shown as failure.
- History: search/filter by platform, status, game, question, date; CSV/JSON export from the ledger; confirmed permalinks and timestamps (local + UTC).

### Health and controls

Shown separately and never merged: **Posting test passed** (first posting-test receipts), **Currently authenticated** (token health files, renewal failure markers, Facebook data-access deadline), **Recurring publishing enabled** (config paused + `PAUSED` + channel flags + timer state). Also: publisher/monitor/renewal timer states and last results (`systemctl show`, no journal access), `health.json` freshness, monitor freshness, Pages deployment budget, Buffer call budget, storage free, media delivery status per job.

Pause: UI writes `PAUSED` (existing sentinel; the runner checks it between jobs). Resume is the sudo activation path. Errors are mapped from ledger categories (`authorization`, `rejected`, `budget`, `media`, `rate_limit`, `uncertain_response`, `missed_slot`, `retry_limit`) to plain-language text and a safe next action.

Backup: UI download of a consistent ledger snapshot (`operations.backup`), library index, manifests and metadata; no credentials (none exist in config). Reboot recovery: units restart cleanly; the runner's reconciliation already handles interrupted dispatches; `.part` cleanup at UI start.

### Security

- Passcode: root-owned `/etc/scalar-social/credentials/UI_PASSCODE`, delivered by `LoadCredential`, entered with `credential_entry.py`. Compared in constant time. Backoff per client using `X-Forwarded-For` only when the peer is loopback.
- Every state-changing request needs the Bearer passcode, `X-Scalar-Request: 1`, and a same-origin `Origin`. Responses carry CSP `default-src 'self'`, `X-Content-Type-Options`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` for API.
- Responses, logs and exports never include credential values, vendor response bodies or credential paths' contents. Tests assert this.
- Unit hardening like the existing units: `NoNewPrivileges`, `ProtectSystem=strict`, `ReadWritePaths=/var/lib/scalar-social`, `ProtectHome`, `PrivateTmp`, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `MemoryMax=96M`.

## Polls and comments

Research of official docs on 6 October (no logins, nothing posted). V = documented, A = absent from docs, I = inferred.

| Platform (route) | Native poll on our route | Own comment/reply on our route | Plan |
|---|---|---|---|
| Instagram Reels (direct) | No: no poll/quiz/sticker publishing parameter (A) | Yes: `POST /{ig-media-id}/comments`; `instagram_business_manage_comments` already granted (V). No pin API (A) | Choices in caption + own first comment with choices; pin manually if wanted |
| Facebook Page Reels (direct) | Ordinary posts no (A). `/{video-id}/polls` (question, options, `correct_option`) exists for videos; Reels support and required permission undocumented (I) | Needs `pages_manage_engagement` (V), which we don't hold | Choices in caption only. Comment and video-poll need a separate owner grant decision; not part of this build |
| Threads (direct) | Yes on TEXT posts only, 2–4 options of 1–25 chars; not on VIDEO (V). A TEXT reply carrying a poll is undocumented (I) | Yes: reply via `reply_to_id`; needs `threads_manage_replies` (V); 1,000 replies/24 h | VIDEO post + companion reply. Try the reply as a native poll; if unaccepted, a text reply listing the choices |
| YouTube Shorts (Buffer) | No community-post API (A) | Not via Buffer (no `firstComment`, V). Direct needs our own `youtube.force-ssl` OAuth | Choices in title/description only |
| X (Buffer) | No poll field in Buffer (V); direct X polls can't carry media and API posting is paid (V) | Buffer `twitter.thread[]` publishes item 2 as an immediate reply (V); no delayed reply | Choices in caption; optional thread item 2 with choices |
| Bluesky (direct) | No polls in the lexicon (A) | Yes: reply with `reply.root/parent` strongRefs (V) | Choices in caption + optional reply with choices |
| TikTok (blocked) | No (V) | No comment-create API (V) | Caption only, when the route exists |

Buffer's API has `firstComment` only for Instagram/Facebook/LinkedIn; we use direct routes for those, so it doesn't apply.

Rules:

- Choices are always in the caption ("A) … B) … C) — comment your letter"), spoiler-free. This works without any permission.
- Companion posts (`poll`, `comment`, `answerReply`) are separate ledger jobs with their own `episode` key (`<questionId>#poll`, `#comment`, `#answer`). The unique constraints still prevent duplicates. They are held until the parent job is `confirmed`, bound by the same approval, and shown in the preview with their exact text. A failed companion never re-posts the parent.
- Companion support is a per-route capability flag. Threads poll-reply starts `unverified`, and the generator uses the text-reply fallback until a separately approved acceptance test confirms it. Facebook comments and video polls stay `unavailable` until the owner decides on a grant change; this build changes no grants or scopes.
- An optional delayed answer reply (Threads, Bluesky, Instagram) is off by default. When enabled, it opens with a spacer line so a relevance-sorted comment list doesn't show the answer first. The answer never goes in the first comment or X thread item 2.
- Prompt for single-letter answers so comment-read APIs can later count guesses. Engagement read-back belongs to the measurement phase, not this build.
- Burning A/B/C choices and a "comment your letter" prompt into the video is recommended for the creative phase (VIDEO_GENERATION_PIPELINE.md decision, not made here).
- Answer-page links (`/:game/answer/:date`) exist only for Daily content. Evergreen library questions have none, so they aren't used by default.

Open: whether a Threads TEXT reply accepts `poll_attachment`; whether `/{video-id}/polls` works on Page Reels and with which permission; whether `pages_manage_engagement` triggers Meta app review; whether a dedicated YouTube `force-ssl` OAuth is worth it.

## Verification

- Python unittest: upload streaming/limits/interruption, path traversal/unexpected-file rejection, merge rules, free-space refusal, hash dedupe, existing-media registration, contract validation (spoilers, lengths, choices), per-platform media eligibility, generator determinism and DST (spring-forward/fall-back in America/New_York), history/duplicate exclusion incl. previous account IDs, exhaustion, approval binding (hash mismatch, stale scope), cancel/edit immutability, lock contention, auth/CSRF/origin/backoff, no-credential-leak assertions.
- Frontend: strict `tsc`, ESLint, Vitest for formatting/time display, Playwright mobile smoke (375×812) against the backend with fixtures.
- Existing suites keep passing: `python3 -m unittest discover -s publisher/tests -p 'test_*.py'`, `node --test tests/social/content.test.mjs` (removed with the legacy bank in the 2026-10 rebuild), `git diff --check`.
- ARM64 run of the Python suite on the Pi in staging.
- Demo (L10): on the Pi, UI against `~/.scalar-social-staging/ui-demo` with a WAL-safe ledger snapshot (owner-run sudo, read-only backup API) → upload a real existing video → media review → generated draft → approval-ready queue. Approval stops before Pages deploy/config write. No social post.

## Installation (requires owner approval before running)

One owner-run command from the staged copy: `sudo sh publisher/deploy/install-ui-paused.sh`. It will:

1. Refuse to run if `scalar-social.timer` is active or config is unpaused.
2. Install code and `ui/dist` to `/opt/scalar-social`; create `/var/lib/scalar-social/{library,manifests}` owned by `scalar-social`.
3. Install `scalar-social-ui.service` (enabled), `scalar-social-approve.path/.service`; add `UI_PASSCODE` credential (owner enters it with `credential_entry.py`).
4. Switch `scalar-social.service` ExecStart to `--manifest` (inert while the timer is disabled).
5. Check `/etc/scalar-social/config.json` is `0640 root:scalar-social` and report (not silently change) anything else.
6. Leave Tailscale Serve, router, credentials' permissions, pause state, channels and the publisher timer unchanged; print the URL and the verification steps.

## Build phases

1. Contract: `library_contract.py` (`validate`, `finalize`) per BATCH_CONTRACT.md, fixtures, tests.
2. Backend core: auth, library import/upload, validation, existing-media registration.
3. Generator + drafts.
4. Approval applier, manifest mode, companion jobs, cancel/edit.
5. Dashboard/history/health/export/backup endpoints.
6. Frontend.
7. Tests, ARM64 run, staging demo.
8. Install proposal → owner approval → install → post-install verification (still paused).

## Reuse from StudioZero

`../StudioZero` (stock-footage recaps and AI animation series) was reviewed on 6 October. Its creative stack — LLM scripts, Gemini TTS narration, Pexels footage, paid Veo/fal.ai generation, Groq captions, karaoke subtitles — conflicts with D14 (no voiceover), D17 (vector/typographic art, no photos), deterministic captions and the no-runtime-AI rule, so none of it enters the pipeline or the Pi.

Worth carrying over as patterns (rewritten to this project's stdlib/Remotion conventions, not imported):

- `src/pipeline_state.py`: per-step started/completed/failed checkpoints with error text → per-episode status in the Mac packager and the Pi import report.
- `src/tools/model_compare.py` HTML report → static review sheet in `library/<batchId>/review/` (covers, key frames, metadata, validator results) for the Mac pilot/QA review before upload.
- `src/marketing.py` hashtag maps → optional per-game hashtag sets in the caption templates. Its LLM caption generation may only be used on the Mac to propose alternatives that are reviewed like any other copy.
- `src/renderer.py` audio mixing (sidechain ducking, ffmpeg capability checks) → reference only if music + SFX mixing needs it in `engines/motion/render/render.sh`; no loudness/ducking runs on the Pi.

Not reused: Google Sheets/Drive job intake (direct Mac → Pi upload chosen), budget guard (no paid generation), FastAPI/WebSocket dashboard (Pi backend stays stdlib).

Account history: the Instagram/Threads/TikTok handles are `studiozeroflow` and TikTok still shows "Movie recaps". Earlier StudioZero posts remain on those accounts; the Scalar-vs-Studio-Zero branding decision in the private PROFILE_REVIEW record is still open and does not block this build.

## Open items outside this build

- `/etc/scalar-social/config.json` was found `0600 root:root` at 22:00 on 6 October after the Instagram install; the monitor fails closed until it is `0640 root:scalar-social`.
- First real Instagram/Threads token renewals (due ≈04:30–04:50 on 7 October) remain unverified.
- TikTok: Buffer support response pending; keep the Buffer Instagram connection until resolved.
- Mac monthly `com.scalar.social.replenish` job conflicts with D23 (no automatic replenishment); reconcile when the creative phase starts.
- Independent backup destination (D20) unresolved.

## Implementation status (7 October 2026)

Built in this repository (uncommitted), nothing installed, nothing published. Publisher still paused, channels disabled, `scalar-social.timer` disabled.

| Phase | State | Where |
|---|---|---|
| 1 Contract | Done | `contract/library_contract.py` (`validate`, `finalize`, media rules, spoiler gate, platform limits) |
| 2 Backend core | Done | `ui_server.py` (auth/CSRF/origin/backoff, signed media URLs with Range), `ui_library.py` (streaming upload, merge rules, dedupe, legacy registration, phone upload, content approval) |
| 3 Generator + drafts | Done | `ui_schedule.py` (deterministic, DST, history incl. `previousAccountIds`, provider caps, exhaustion, edits, `carryOnly`) |
| 4 Approval, manifest, companions, cancel/edit | Done | `ui_approval.py`, `approval_bind.py` (root step), `activate.py`, `resolve_job.py`, runner companion hold, adapter replies/comments, `scalar-social.service` → `--manifest` |
| 5 Dashboard/history/health/export/backup | Done | `ui_health.py`, `ui_views.py` |
| 6 Frontend | Done | `publisher/ui/` (React 19, Vite, strict TS; ~90 KB gzipped JS) |
| 7 Tests, ARM64, staging demo | Done | Python suite on Mac and Pi ARM64; Vitest/tsc/ESLint; Playwright mobile smoke against the real backend; Pi staging demo with no deploy |
| 8 Install | Done 7 Oct 21:22 EDT, owner-run; post-install checks passed (UI healthy, API requires the passcode, timer disabled, monitor healthy, ledger backup `backup-ui-20261008T012155.sqlite3`) | `publisher/deploy/install-ui-paused.sh` |

Deviations and findings, decided in code rather than by changing locked decisions:

- Contract media rule `yuv420p` is enforced for new batches; the published 2026-10-05 renders are full-range `yuvj420p` and are tolerated only as `legacy-2026-10-05`. Remotion output must be converted (`-vf scale=in_range=pc:out_range=tv -pix_fmt yuv420p -color_range tv`).
- Spoiler gate reading: the answer may appear once, only inside a complete choice list (as in the contract's own example caption).
- Threads companion replies need `threads_manage_replies`, which the current grant lacks; the generator excludes them with that reason. X thread item 2 is coded but gated by `buffer_adapter.X_THREAD_VERIFIED = False` until a live acceptance test. Bluesky replies need the parent's record cid, stored only for posts confirmed after this build.
- The Pi kernel boots with `cgroup_disable=memory`, so `MemoryMax=` in every scalar-social unit (existing and new) is not enforced. Measured peaks fit the Pi: UI ~28 MB RSS, single-threaded ffmpeg cover grab ~91 MB.
- Legacy and phone episodes have no web source; the scalargame.com deep link is recorded as the evidence source and phone uploads are marked owner-attested. A contract field for owner attestation would be more precise (proposal, not changed).
