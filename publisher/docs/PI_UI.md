# Pi management UI — operator guide

Status: built and tested 7 October 2026; **installed by the owner 7 October 2026 21:22 EDT** (`scalar-social-ui.service` and `scalar-social-approve.path` enabled; publisher unit on `--manifest`). Publishing stays paused, all channels disabled and `scalar-social.timer` disabled until the separate activation command. Plan and locked decisions: [PUBLISHING_PIPELINE_PLAN.md](PUBLISHING_PIPELINE_PLAN.md). Mac → Pi interface: [BATCH_CONTRACT.md](../../contract/BATCH_CONTRACT.md).

Address (tailnet only, existing Tailscale Serve): https://<pi>.<tailnet>.ts.net → `127.0.0.1:8765`. Sign in once with the passcode; a secure, HTTP-only browser session remembers the sign-in for up to 90 days. Sign out revokes that browser session. Changing the passcode invalidates existing sessions.

## What it does

1. **Library**: add a Mac batch (drop or choose the finalized folder `library/<batchId>/` once, then Upload batch: the browser checks `READY_FOR_UPLOAD` against `batch.json`, sends `batch.json`, then only the listed `videos/` and `covers/` files, one request per file, hashed while streaming, matched to `batch.json`; `review/` is never sent; failed files retry in place). Mac batches are the only way in (the phone single-video upload was removed in the October 2026 clean pass; older `manual-*` batches stay readable). Every video is re-measured with ffprobe; platforms it fails are disabled for it, with the reason. Existing Pi media is registered once as batch `legacy-2026-10-05` (in place, not copied; questionIds `ep01`–`ep08`).
2. **Content approval** (approval of record): per video or "approve all shown", recording reviewer, time, file hashes, metadata hash and caption hash. Nothing is approved on import.
3. **Schedule**: preset first. New draft shows the recommended plan (one post per platform per day for 21 days, America/New_York, fixed time per platform; rationale in [SCHEDULE.md](SCHEDULE.md)); only the start date and timezone are visible fields. Generate draft builds the inputs from the preset; **Customize** opens the full form (explicit timezone, dates, per-platform days/times/max per day, minimum gap, stagger, companions) already filled with the preset values. Nothing is form state until one of those is tapped, and the preset yields the same draft hash as the form filled by hand with the same values. The deterministic generator produces a draft (same inputs + same library/ledger → same hash), showing each job's local time with zone and UTC, platform, video, exact caption/title/poll/comment, warnings, exclusions and "N of M requested slots fillable". Edit or remove entries → new draft.
4. **Schedule approval**: one tap on Approve (the button sends `APPROVE <first 8 of hash>`; nothing is typed), or the autopilot's refill (`app/autopilot.py`, same request). The approval service re-validates, deploys the referenced media to Cloudflare Pages once, verifies every public URL by hash, writes `manifests/<sha>.json`, a root step records only `approval.manifestSha256` and `approval.approvedAt` in the config, then `activate.py --auto` (root) follows the new schedule unless publishing is paused.
5. **Activation** (owner, outside the UI): the UI shows the readiness checklist and the exact command. Only that command enables the manifest's channels, removes the pause and enables the timer.
6. **Queue, posts, health**: the approved-schedule card (span, hash, next posts) with the queue at `#/schedule/queue`: approved jobs with ledger status; cancel/edit undispatched jobs (creates a new draft that must be re-approved; the old approval stands until then); Activity › Posts (the old History: search, filters under ⋯, CSV/JSON export, desktop table); three separate statuses per platform — *posting test passed*, *currently authenticated*, *recurring publishing enabled* — as three marks in one Home row per platform; timers, monitor, budgets, storage (Settings › System); plain-language errors with the safe next action; uncertain jobs with reconciliation info and no "post again"; Pause; backup download.
7. **Activity** (phone-friendly log): one timeline of every publisher event (queued, sent, confirmed with link, uncertain, blocked, expired, cancelled, owner-resolved), approval results, uploads and content approvals, and the last run of the publisher, monitor, renewals and approval service, plus token-renewal failure markers. Chips (All, Posts, Uploads, Approvals, System), a search box, the other filters and CSV/JSON export under ⋯, older pages. Home and Activity refresh every 30 s while the page is visible (one-line status with a pause toggle). journald and credentials are never read.
8. **Feedback and next batch** (contract: [REBUILD_CONTRACTS.md](../../docs/REBUILD_CONTRACTS.md) §2–3): per-revision feedback (tags from the fixed list, note ≤ 2,000 characters, `open` until marked used; saving again reopens it) and per-batch brief/retro markdown (≤ 65,536 UTF-8 bytes, stored with its sha256). `GET /api/library/episodes/<id>/<rev>` returns the episode exactly as imported (from the stored batch.json), its status, batch notes, feedback and the ledger's own records for it (status, time, permalink; no metrics). `GET /api/next-batch` gives the next `YYYY-MM-bNN` id (current UTC month; NN = 1 + the highest bNN ever imported), open feedback, the latest brief/retro and posted permalinks. The dashboard adds `standing`: last Mac batch (with how many of its episodes still miss files), revisions awaiting review, the next 3 undispatched posts of the approved schedule, open feedback, the next batch id, posts confirmed in the last 7 days and the latest brief/retro times; `src/lib/journey.ts` derives the six-step loop from it. Notes and feedback may name answers: only these endpoints read them; scheduling, approval and publishing never do.
9. **Layout** (clean pass, [PI_UI_REDESIGN_PLAN.md](../../docs/PI_UI_REDESIGN_PLAN.md)): five sections, **Home, Library, Schedule, Activity, Settings**, as a 56 px bottom tab bar on phones (375 px first) and a fixed 220 px left sidebar from 1024 px (same items, order and glyph icons; installed commit at the foot). The header has the brand and a **?** help icon that opens the guide at the current screen's section (`content/guide/meta.json` → `screens`). Every screen has one `h1` (focused after navigation), a step line under it ("Step 3 of 6 · Review"), a collapsed "What to do here" and one primary action: the current step's. Old hashes redirect: `#/dashboard` → `#/home`, `#/history` → `#/activity?tab=posts`, `#/activation` → `#/settings#activation`, `#/next-batch` → `#/library/make`. Desktop: content never wider than 1120 px; Library review and Make a batch use two columns, Schedule shows the draft beside the approval panel.
10. **Post stats** ([MEASUREMENT.md](MEASUREMENT.md)): Library › Make a batch → How the posts did starts with the *Post stats* panel (`src/views/library/PostStatsPanel.tsx`): **Hourly reads** On/Off (a toggle button with a fixed name and `aria-pressed`; buttons use `aria-disabled` while busy so focus stays put; the live region also announces when a read finishes), **Read stats now** with an *Also read past days (0–93)* disclosure, and a status line (last run time, how it started, outcome in words, one word per platform: read / not set up / access refused / can't be read / can't be read (posted through Buffer) / read failed / not readable by the Pi; `src/lib/metricsStatus.ts`). A pending read shows "Waiting for the Pi…" and is polled every 4 s for up to 5 minutes, then a still-waiting note and **Check again**. A notice appears when `scalar-social-metrics.path` is not active. Until YouTube reads `ok` the panel shows the YouTube key command (`enable-metrics.sh --youtube-key`) with Copy, "On the Pi"; afterwards "already stored". Under it, `FunnelTable.tsx`: one row per episode, Views → Avg watch → Engaged → Answered → Follows that day, a per-platform disclosure, "—" for no data, and the notes that follows are account-level for the publish day and that X and TikTok come from Buffer once a day. Settings › System has a read-only *Post stats* block (hourly reads on/off, last run, next timer run, whether read requests are picked up, a waiting request). Endpoints: `GET /api/metrics/status` → `{enabled, pending|null, lastRun|null, timer|null, pathActive}`; `PUT /api/metrics/enabled {enabled}` → status (a switch record only on a change); `POST /api/metrics/read {backfill?}` → 202 with status, 409 while a request waits, 422 for bad input; `GET /api/next-batch` adds `funnel`. Activity (System) shows `system.metrics-on`, `system.metrics-off` and `system.metrics-read-requested`. Boundary: the UI writes only `STATE/metrics/enabled`, `metrics/request.json` and `metrics/history/switch-*.json`; it holds no tokens and has no network. `scalar-social-metrics.timer` and `.path` start `metrics.py`, which does the reading.

## Components

| Piece | Path | Runs as |
|---|---|---|
| Batch contract validator | `contract/library_contract.py` | Mac and Pi |
| UI backend | `publisher/app/ui_server.py` (+ `ui_views.py`, `ui_library.py`, `ui_schedule.py`, `ui_health.py`) | `scalar-social-ui.service`: `scalar-social`, loopback, `MemoryMax=96M`, no outbound network (`IPAddressDeny=any`) |
| Frontend | `publisher/ui/` (React 19, Vite, strict TS), built on the Mac into the committed `publisher/app/static/` (`npm run build:static`) → `/opt/scalar-social/ui` | static files served by the backend |
| Approval applier | `publisher/app/ui_approval.py` via `scalar-social-approve.path` → `.service` | `scalar-social` + `CLOUDFLARE_API_TOKEN`; `ExecStartPost=+approval_bind.py` (root) writes only the two approval fields |
| Activation | `python3 -I -B publisher/app/activate.py --check` / `--apply --confirm-zero-spend` | owner `sudo` |
| Reconciliation | `python3 -I -B publisher/app/resolve_job.py <job> --confirmed --permalink URL --evidence TEXT` or `--not-published --evidence TEXT` | owner `sudo` |
| Publisher | existing `runner.py` via `monitored.py tick --manifest /var/lib/scalar-social/manifests/approved.json` | unchanged user and credentials |
| Post stats reader | `publisher/app/metrics.py collect` via `scalar-social-metrics.timer` (hourly :20) and `scalar-social-metrics.path` (UI read request) → `.service` | `scalar-social` + the stats tokens (`LoadCredential=`); read-only, never publishes or writes the ledger |

State (all under `/var/lib/scalar-social`, owned by `scalar-social`): `library/index.sqlite3` (batches, episodes, videos, covers, approvals, drafts, manifests, feedback, batch_notes; new tables are added on open with `CREATE TABLE IF NOT EXISTS`), `library/objects/<sha256>.mp4`, `library/covers/<sha256>.jpg`, `library/.incoming/*.part` (removed at start and after 6 h), `manifests/`, `approval/{request,result}.json` + `approval/history/`, `site/library/` (hard links deployed to Pages), `metrics/` (post stats switch, read requests and last run; [MEASUREMENT.md](MEASUREMENT.md)). The ledger stays the only posting history; drafts never enter it.

## Companion posts

Separate ledger jobs keyed `<questionId>#comment|#answer|#poll`, held until the parent post is `confirmed`, bound by the same approval, never re-posting the parent:

| Route | Companion | State |
|---|---|---|
| Instagram (direct) | own first comment | available (`instagram_business_manage_comments` granted) |
| Threads (direct) | text reply; poll reply sent as text | needs the `threads_manage_replies` grant — **not held**, so the generator excludes it with that reason |
| Bluesky (direct) | reply | available for posts confirmed after this build (needs the stored record cid) |
| X (Buffer) | thread item 2 | code ready; `buffer_adapter.X_THREAD_VERIFIED = False` until a live acceptance test, so the generator skips it with a warning |
| Facebook, YouTube, TikTok | none | unavailable (no grant / no API route) |

## Install (owner, once; publishing stays paused)

> Since the rebuild (October 2026) the Pi runs from a git checkout: run `publisher/deploy/bootstrap-git.sh` once, then update from Settings → Update. See [SELF_UPDATE.md](SELF_UPDATE.md). The copy installer below is the historical first install; it refuses to run once `/opt/scalar-social/repo` exists.

From a staged copy of this repo on the Pi (the 7 October install ran from `~/.scalar-social-staging/ui-install/`, old layout):

```bash
sudo sh <staged copy>/publisher/deploy/install-ui-paused.sh
```

It refuses unless the timer is disabled/inactive, config paused with all channels disabled and `PAUSED` present, and the live `scalar-social.service` matches the reviewed version. Then it: backs up the ledger; copies the publisher unit to root-only `/var/backups/scalar-social`; installs `publisher/app/*.py` + `contract/library_contract.py` and the committed UI bundle `publisher/app/static/`; creates the state folders; installs `scalar-social-ui.service`, `scalar-social-approve.path/.service` and the `--manifest` publisher unit (credential drop-ins untouched); asks for the UI passcode (hidden; 4 or more characters, a 4-digit PIN is fine) if missing; reports config permissions; enables and starts the UI service and the approval path; prints health, unit status and timer state.

Uninstall/rollback: `sudo systemctl disable --now scalar-social-ui.service scalar-social-approve.path`; restore the root-only copy `/var/backups/scalar-social/scalar-social.service.before-ui-*` to `/etc/systemd/system/scalar-social.service`; `sudo systemctl daemon-reload`.

## Recovery

- Reboot: the UI unit restarts; partial uploads are deleted at start; the publisher's existing reconciliation handles interrupted dispatches.
- Interrupted upload: the file shows as missing; select it again (already-present files are skipped by hash).
- Failed approval: the result explains why (busy publisher, stale draft, media check, deployment budget…); fix and approve again. A failed approval changes no manifest, ledger or config.
- Uncertain job: check the platform profile; record the outcome with `resolve_job.py`. Never post it again by hand.

## Tests

```bash
python3 -m unittest discover -s publisher/tests -p 'test_*.py'
python3 -m unittest discover -s contract/tests -p 'test_*.py'
cd publisher/ui && npm run typecheck && npm run lint && npm test && npm run build
npm run build:static   # after any UI change: rebuild the committed bundle publisher/app/static (+ MANIFEST.json)
npm run check:static   # fails if the committed bundle does not match a fresh build of the current source
```
Playwright (mobile 375×812 and desktop 1440×900) against a real backend on throwaway fixture state, never real state:

```bash
python3 publisher/tests/ui_fixture_state.py --out /tmp/pi-fixture --source library/2026-10-b01   # prints the fixture passcode
python3 contract/library_contract.py finalize /tmp/pi-fixture/work/2026-10-second               # for the journey spec only
CREDENTIALS_DIRECTORY=/tmp/pi-fixture/credentials python3 publisher/app/ui_server.py --state /tmp/pi-fixture/state \
  --config /tmp/pi-fixture/config.json --update-state /tmp/pi-fixture/update --allowed-origin http://127.0.0.1:8765 --no-legacy
cd publisher/ui && npx playwright install chromium   # once
SCALAR_UI_URL=http://127.0.0.1:8765 SCALAR_UI_PASSCODE=<fixture passcode> SCALAR_UI_JOURNEY_BATCH=/tmp/pi-fixture/work/2026-10-second npm run e2e
```

Specs: `smoke` (every screen, no horizontal scroll, 44 px buttons, preset = Customize = hand-typed inputs give the same draft hash), `keyboard` (focus on the title, chips and disclosures by keyboard), `guide`, `stats` (Post stats switch on/off, Read stats now stays pending because no path unit runs locally, the path notice, funnel notes, no horizontal scroll, the Settings › System block; writes only the fixture's `STATE/metrics/`), and `journey` (Home → Make a batch → upload → review/approve → schedule → typed phrase → Settings › Activation; it writes to the fixture, so it runs only with `SCALAR_UI_JOURNEY_BATCH`). `SCALAR_UI_BROWSER_CHANNEL=chrome` uses installed Google Chrome instead (decodes H.264). Badge contrast (≥ 4.5:1, light and dark) is a Vitest test (`src/styles.contrast.test.ts`).

## Screens (after the clean pass; UI side of docs/REBUILD_CONTRACTS.md)

One progress model: `src/lib/journey.ts` turns the dashboard payload (plus the browser-local Make checklist, `localStorage` `scalar-make-<batchId>`) into the six steps **Make → Upload → Review → Schedule → Post → Learn**, each `todo / current / done / blocked`, and the one current step with its action (priorities documented in the file; `nextStep.ts` is a small adapter). Home, the step lines and the empty states all read it.

- **Home** (`#/home`): *Your loop* — the six steps as a strip (tap one for its fact; blocked steps say why and who) with the current step expanded and its one button; *Attention* (uncertain jobs, warnings/errors, token renewals or expiries within 7 days, an available update; hidden when empty, never repeating the current step); *Platforms* — one row per platform with three separate marks (posting test · authenticated · recurring), tap for the details.
- **Library** (`#/library`): + Make a batch (primary when nothing waits for review), the drop zone (drop the batch folder anywhere on the page, or choose it; per-file list behind a disclosure), batch chips, To review / Approved / All chips (default To review), one tap-to-review card per episode, Approve all shown in a sticky bar (To review, ≥ 2 shown), Free space behind a disclosure.
- **Episode** (`#/library/episode/<episodeId>/<revision>`): player, question, clues and choices, status; a sticky bar with **Approve** (existing confirmation, reviewer name in the dialog), **Feedback** (bottom sheet on phones, inline on desktop) and **Next →** through the list you came from (remembered for the tab; an episode just approved keeps its place); disclosures for posts and captions, answer and evidence (Reveal answer resets per episode), platform eligibility, measured media, batch notes, history and Withdraw/Delete. Desktop adds the list on the left.
- **Make a batch** (`#/library/make`): five numbered steps, each labelled here on the Pi or on the Mac: carry feedback over (open feedback, last brief/retro and How the posts did behind disclosures, the last with the Post stats panel, the funnel and Accounts, last 7 days; Download `feedback-<id>.json`), write the brief (Copy prompt for Claude, the one primary action), let Claude make it (Mac commands with Copy, a checkpoint checklist kept in this browser and cleared once the batch arrives), upload it (the same drop zone), retro after posting (Mac command, the batch's notes, Mark feedback as used).
- **Schedule** (`#/schedule`, `#/schedule/queue`): approved-schedule card, New draft (preset first; Customize), draft preview and the approval panel (one-tap Approve; no typed phrase since 2026-10-09); on phones a sticky "Go to approval ↓".
- **Activity** (`#/activity`, `?tab=posts|uploads|approvals|system`): chips, search, ⋯ menu, the job detail drawer.
- **Settings** (`#/settings#control|activation|update|system|backup|session`): one anchored page with a section index on desktop. Publishing control (Pause, confirm as before), Activation (readiness checklist and owner commands, displayed only), Update (installed vs latest commit, Check for updates, What's new, warnings, unit/pi-package command, Update after reviewing the pinned full SHA; the backend still requires `UPDATE TO <full sha>`; sessionStorage `scalar-update-baseline` reloads the page once the new commit runs; the UI never contacts GitHub), System (jobs needing reconciliation and issues open when present; timers, health, budgets, storage and Post stats collapsed), Backup, Session.
- **Guide** (`#/guide/<anchor>`): `publisher/ui/content/guide/*.md` + `meta.json`, bundled at build time and rendered by a small Markdown-subset renderer (no HTML); opened from the header **?**. `src/lib/guide.test.ts` fails if an anchor, an in-guide link or a screen's help anchor is missing.
