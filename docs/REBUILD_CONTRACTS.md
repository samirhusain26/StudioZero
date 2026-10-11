# Rebuild contracts (Phases 3–6)

Fixed interfaces shared by the parallel builders: Pi update backend, library backend, UI, and skill/guide. If one of these must change, change it here first and tell the integrator. Plan: [REBUILD_PLAN.md](REBUILD_PLAN.md).

All `/api/*` routes are session-gated, with Bearer passcode retained for existing clients. `GET /api/session` reports cookie session validity; `POST /api/session` exchanges a valid Bearer passcode for an opaque, persistent HttpOnly SameSite=Strict cookie (90-day expiry); `DELETE /api/session` revokes it. Only a SHA-256 token digest, expiry, and HMAC passcode binding are stored in a private SQLite database under the UI state directory. Changing the passcode invalidates prior sessions. Session mutations and all other writes need `X-Scalar-Request: 1` and an allowed `Origin`. Errors use the existing JSON error shape. Timestamps are UTC ISO-8601 with `Z`.

## 1. Pi self-update (Phase 3, backend `publisher/app/updater.py`)

### Pi layout after bootstrap

- Users (L15, second security review): the checkout `/opt/scalar-social/repo` is owned by the system user `scalar-social-update` (no login, home `/nonexistent`, in no scalar-social group), which runs only the update unit. Dirs 0755, files 0644: the scalar-social services run and serve it but cannot write it. Partial clone (`--filter=blob:none`) with sparse cone `publisher/` and `contract/`. Branch `main`.
- Runtime: units run `/opt/scalar-social/repo/publisher/app/*.py`. The UI serves `/opt/scalar-social/repo/publisher/app/static`. Node deps for wrangler stay in `/opt/scalar-social/node_modules` (owner-managed; never changed by the updater). Every root-run Python uses `python3 -I -B` (the scripts add their own folder to `sys.path`).
- Deploy key and git/ssh config: root-owned folder `/etc/scalar-social-update` (root:scalar-social-update 0750) holding `deploy_key` (root:scalar-social-update 0640; OpenSSH only checks key permissions when the key belongs to the user running ssh; scalar-social cannot read it), `deploy_key.pub`, `ssh_config` (`Host github.com-scalar`: HostName github.com, User git, IdentitiesOnly yes, IdentityAgent none, UserKnownHostsFile `/etc/scalar-social-update/known_hosts`, GlobalKnownHostsFile /dev/null, StrictHostKeyChecking yes, BatchMode yes) and `known_hosts` (GitHub's published keys), root:root 0644. Every updater git call runs with `HOME=/etc/scalar-social-update`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, hooks and fsmonitor off, `protocol.file.allow=never` (tests only: `user`), and `GIT_SSH_COMMAND="ssh -F /etc/scalar-social-update/ssh_config"`. Origin URL is `git@github.com-scalar:samirhusain26/scalargame-marketing-plan.git` (the current GitHub name); the updater also accepts `scalargame-marketing` in case the owner renames it.
- Update state: `/var/lib/scalar-social-update/` (scalar-social-update, 0755) holds `status.json` and `units-applied.json` (0644, written only by the update user; the UI reads them). Its `inbox/` (scalar-social-update:scalar-social, 1730) is the only place the UI writes: `request.json` (ignored when its `requestedAt` is over 15 minutes old) and `ui.json` (`{requestId, phase: "restarting"|"serving", running, at}`). Staging worktrees go in `/opt/scalar-social/repo/.git/scalar-update-stage/stage-*`. The publisher's `/var/lib/scalar-social/runner.lock` is 0644 and its folder 0711 (`StateDirectoryMode=0711` in `scalar-social.service`), so the update user can flock it read-only; without it the update refuses to switch.
- Units: `scalar-social-update.path` (`PathExists=/var/lib/scalar-social-update/inbox/request.json`) starts `scalar-social-update.service` (`TriggerLimitIntervalSec=60`, `TriggerLimitBurst=20`, so a request the service refuses cannot loop). That service is oneshot, `User=scalar-social-update`, has network, `HOME=/etc/scalar-social-update`, `UMask=0022`, `MemoryMax=256M`, `TimeoutStartSec=60min`, `ProtectSystem=strict`, `ReadWritePaths=/var/lib/scalar-social-update /opt/scalar-social/repo`, `NoNewPrivileges=true`. Its first step renames `request.json` to `request.taken.json`, so the path unit cannot loop; a request queued while it finishes is handled by the same run. `scalar-social-ui.service` is `Type=notify` (`READY=1` once listening, `TimeoutStartSec=90`), `StartLimitIntervalSec=300`, `StartLimitBurst=30`, `ReadWritePaths=/var/lib/scalar-social -/var/lib/scalar-social-update/inbox`.
- The UI unit keeps `IPAddressDeny=any` and never fetches. It reads HEAD from the git files and runs git only offline with `-c safe.directory=/opt/scalar-social/repo`; it writes only `inbox/request.json` and `inbox/ui.json`.
- Restart: the UI process watches `status.json`. When `phase == "switched"` and on-disk HEAD differs from the running commit (full SHAs), it writes `ui.json` `restarting` and calls `os._exit(86)`. `Restart=on-failure` restarts it. At startup, once the HTTP socket listens, `reconcile()` writes `ui.json` `serving` and the UI sends `READY=1`. The API overlays `ui.json` on `status.json` (`updater.current_status`): `restarting`, then `complete` if the running commit equals `toCommit`, otherwise `failed`.
- Automatic rollback: after a switch the update unit waits up to 30 s for `restarting`, then up to 120 s for `serving`, and writes `complete`. If `restarting` came but `serving` did not, it resets to `fromCommit` (no fetch, SIGTERM ignored meanwhile) and writes `failed` ("The UI did not come back on … within 120 s; rolled back to …"). A UI running `toCommit` that then sees `failed` with HEAD = `fromCommit` exits 86 without writing anything.
- The running commit is read once, at import of `ui_server.py` when run as the program (before the other app modules load). It is `null` when the code is not running from a git checkout (`installKind: "copy"`).
- Unit or `pi-package*.json` changes are never applied automatically. The status shows `applyUnitsCommand: "sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh"`.

### Endpoints

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/system/update/status` | `UpdateInfo`. No side effects. |
| POST | `/api/system/update/check` | Queues `{action:"check"}`. 202 `{queued:true}`. 409 `{code:"busy"}` while a request is pending or phase ∈ staging…restarting. 409 `{code:"not_git"}` for `installKind:"copy"`. |
| POST | `/api/system/update/start` | Body `{confirm:"UPDATE TO <40-hex sha>"}`. The UI constructs this value from the full SHA pinned when its confirmation dialog opens. Requires: the last check is ≤ 15 min old, `fetchOk`, `!dirty`, `!diverged`, `branchOk`, `originOk`, `behind > 0`, and the sha equals `check.origin`. Then queues `{action:"apply", sha}` and returns 202. Errors: 400 `bad_confirm`; 409 with `code` ∈ `stale_check`, `dirty`, `diverged`, `origin`, `branch`, `up_to_date`, `busy`, `not_git`. |

```ts
export type UpdatePhase = 'idle' | 'checking' | 'checked' | 'staging' | 'waiting' | 'switching' | 'switched' | 'restarting' | 'complete' | 'failed'
export interface UpdateCommit { sha: string; subject: string; date: string }
export interface UpdateCheck {
  checkedAt: string; fetchOk: boolean; head: string; origin: string | null
  behind: number; ahead: number; dirty: boolean; diverged: boolean; branchOk: boolean; originOk: boolean; originUrl: string
  incoming: UpdateCommit[]            // newest first, max 30
  changes: { units: boolean; piPackage: boolean; contract: boolean; ui: boolean; files: string[] }  // files max 100
  error: string | null
}
export interface UpdateStatus {
  phase: UpdatePhase; requestId: string | null; startedAt: string | null; updatedAt: string | null
  fromCommit: string | null; toCommit: string | null; error: string | null
  log: string[]                       // last ≤ 40 lines, secrets never included
  check: UpdateCheck | null
}
export interface UpdateInfo {
  runningCommit: string | null; installKind: 'git' | 'copy'; repoHead: string | null
  restartNeeded: boolean              // repoHead !== runningCommit
  unitsChanged: boolean; piPackageChanged: boolean  // since the running commit's install of units (last apply)
  applyUnitsCommand: string | null    // shown when unitsChanged || piPackageChanged
  status: UpdateStatus
}
```

### Apply sequence (`updater.py apply`)

1. `fetch origin main` with low-memory git config (`pack.threads=1`, small window/delta caches).
2. `rev-parse origin/main` must equal the requested sha; otherwise fail with "origin changed after confirmation".
3. Require `merge-base --is-ancestor HEAD <sha>`, a clean tree, the right branch and the right origin.
4. Phase `staging`: `worktree add --detach <stage> <sha>`, then run the staged checks:
   - `python3 -m compileall -q publisher/app contract`
   - import every `publisher/app/*.py` module in a subprocess with the stage on `sys.path`
   - the contract tests plus a quick publisher subset (must pass without `studio/`)
   - `publisher/app/static` matches its `MANIFEST.json` (Python check)
5. Phase `waiting`: open `/var/lib/scalar-social/runner.lock` read-only (`O_NOFOLLOW|O_NONBLOCK`, regular file) and take a non-blocking flock, retrying for up to 10 min, and hold it through the switch. On timeout, fail with "Publisher is running a post; try again later". Never start the switch with less than 5 min before the unit timeout.
6. Phase `switching`: `merge --ff-only <sha>`. On any failure (SIGTERM included), `reset --hard <old>`.
7. Phase `switched`. Remove the worktree and prune, always (in a `finally`). Never `git pull`. Then the restart verification above.

## 2. Library features (Phase 4/5, backend `ui_library.py` / `ui_views.py` / `ui_server.py`)

Storage: the existing `library/index.sqlite3`, extended with `CREATE TABLE IF NOT EXISTS` (the existing pattern) and covered by tests.

Allowed feedback tags (decision L10): `keep, tweak, drop, hook-weak, too-hard, too-easy, great-reveal, visual-issue, fact-check, music`. Note ≤ 2,000 characters.

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/library/episodes/<episodeId>/<revision>` | `EpisodeDetail` |
| PUT | `/api/library/episodes/<episodeId>/<revision>/feedback` | Body `{tags, note}`. Upserts the row (status set to `open`). Returns `EpisodeFeedback`. |
| DELETE | `/api/library/episodes/<episodeId>/<revision>/feedback` | Clears it. 204. |
| POST | `/api/feedback/mark-used` | Body `{items:[{episodeId, revision}]}`. Sets status `used`. Returns `{updated:n}`. |
| GET | `/api/library/batches/<batchId>/notes` | `BatchNotes` |
| PUT | `/api/library/batches/<batchId>/notes/(brief\|retro)` | Body `{text}`, UTF-8, ≤ 65,536 bytes. Returns `BatchNote`. 404 for an unknown batch. Notes may contain answers; they are never published. |
| GET | `/api/next-batch` | `NextBatchInfo` |
| GET | `/api/dashboard` | Existing response plus `standing: Standing` |

```ts
export const FEEDBACK_TAGS = ['keep', 'tweak', 'drop', 'hook-weak', 'too-hard', 'too-easy', 'great-reveal', 'visual-issue', 'fact-check', 'music'] as const
export type FeedbackTag = (typeof FEEDBACK_TAGS)[number]
export interface EpisodeFeedback { episodeId: string; revision: number; tags: FeedbackTag[]; note: string; status: 'open' | 'used'; updatedAt: string }
export interface BatchNote { batchId: string; kind: 'brief' | 'retro'; text: string; sha256: string; bytes: number; uploadedAt: string }
export interface BatchNotes { batchId: string; brief: BatchNote | null; retro: BatchNote | null }
export interface PostMetrics { checkpoint: string; fetchedAt: string; status: string; values: Record<string, number> }  // newest read by metrics.py
export interface EpisodePost { platform: string; status: string; at: string | null; permalink: string | null; metrics: PostMetrics | null }
export interface EpisodeDetail {
  batchId: string
  episode: Record<string, unknown>    // the full batch.json episode object, as imported (creative, evidence, music, video, cover, publication, eligibility, …)
  approval: { status: string; at: string | null } | null
  notes: BatchNotes
  feedback: EpisodeFeedback | null
  posts: EpisodePost[]
}
export interface FeedbackItem extends EpisodeFeedback { batchId: string; questionId: string; game: string; format: string; styleId: string }
export interface NextBatchInfo {
  nextBatchId: string                 // YYYY-MM-bNN: the current UTC month, NN = 1 + the highest bNN seen in any month (zero-padded to 2)
  openFeedback: FeedbackItem[]
  lastBrief: BatchNote | null; lastRetro: BatchNote | null   // from the most recently imported batch that has them
  performance: EpisodePost[]          // posted jobs with permalinks; empty if none
  accounts: AccountStats[]            // { platform, followers, followersChange, days, totals, status } over the last 7 days
  tags: FeedbackTag[]
}
export interface Standing {
  lastBatch: { batchId: string; importedAt: string; episodeCount: number; awaitingFiles: number } | null   // excluding legacy-*/manual-*; awaitingFiles = its episodes still missing a video or cover
  awaitingReview: number              // imported, verified, not yet content-approved
  nextPosts: { at: string; platform: string; episodeId: string }[]   // ≤ 3, from approved schedules
  openFeedback: number
  // Added for the loop (docs/PI_UI_REDESIGN_PLAN.md §0, publisher/ui/src/lib/journey.ts); read-only, no new state:
  nextBatchId: string | null          // same id as GET /api/next-batch
  postedLast7Days: number             // confirmed posts (not companions) published in the last 7 days
  lastBriefAt: string | null          // uploadedAt of the latest non-empty brief / retro
  lastRetroAt: string | null
}
```

## 3. Next-batch hand-off (UI → Mac skill)

"Copy prompt for Claude" copies exactly this:

```
/video-batch brief <nextBatchId>

<brief markdown as edited on the page>

Feedback file: library/_inbox/feedback-<nextBatchId>.json
```

"Download feedback.json" saves `feedback-<nextBatchId>.json`. The owner puts it in `marketing/library/_inbox/`, which is gitignored.

```json
{
  "schemaVersion": 1,
  "kind": "scalar-next-batch-feedback",
  "exportedAt": "2026-11-02T18:00:00Z",
  "fromCommit": "<running commit or null>",
  "nextBatchId": "2026-11-b02",
  "brief": "<markdown>",
  "lastRetro": { "batchId": "2026-10-b01", "text": "<markdown>" },
  "feedback": [ { "episodeId": "…", "revision": 1, "batchId": "…", "questionId": "…", "game": "…", "format": "…", "styleId": "…", "tags": ["hook-weak"], "note": "…", "updatedAt": "…" } ],
  "performance": [ { "platform": "…", "status": "…", "at": "…", "permalink": "…", "metrics": { "checkpoint": "24h", "fetchedAt": "…", "status": "ok", "values": { "views": 1500, "likes": 30, "answers.B": 4 } } } ],
  "accounts": [ { "platform": "instagram", "followers": 120, "followersChange": 20, "days": 7, "totals": { "impressions": 6300, "engagements": 315, "engagement_rate": 0.05 }, "status": "ok" } ]
}
```

## 4. Guide (Phase 4/6)

- Source: `publisher/ui/content/guide/*.md` plus `publisher/ui/content/guide/meta.json` `{ "updated": "YYYY-MM-DD", "order": ["overview", …] }`. The skill/guide builder owns these files. The UI bundles them at build time with `import.meta.glob(..., { query: '?raw', eager: true })` and never fetches them at runtime. They are part of the UI `sourceHash` (`content/` is an input dir).
- Markdown subset rendered by the UI (no raw HTML): `#`–`###` headings, paragraphs, `-`/`1.` lists, fenced code, inline code, `**bold**`, `[text](url)` links (only `#anchor` and `https:` links), and tables.
- An anchor is the slug of a heading: lowercase, non-alphanumerics become `-`, trimmed. These anchors are fixed; per-screen help links to them, and a test checks every link resolves.

| File | Required headings (anchor) |
|---|---|
| overview.md | How it works (`how-it-works`), Where things live (`where-things-live`) |
| make-a-batch.md | Make a batch (`make-a-batch`), Brief (`brief`), Checkpoints (`checkpoints`), Finalize (`finalize`), Retro (`retro`) |
| upload.md | Upload a batch (`upload-a-batch`), Batch notes (`batch-notes`), Failed upload (`failed-upload`) |
| review.md | Review episodes (`review-episodes`), Feedback (`feedback`), Approve content (`approve-content`) |
| schedule.md | Schedule (`schedule`), Approve a schedule (`approve-a-schedule`), Activation (`activation`) |
| next-batch.md | Next batch (`next-batch`) |
| update.md | Update the Pi (`update-the-pi`), Failed update (`failed-update`), Rollback (`rollback`), Unit files changed (`unit-files-changed`) |
| health.md | Health (`health`), Recovery (`recovery`) |
| owner-only.md | Things only Samir can do (`things-only-samir-can-do`) |
| glossary.md | Glossary (`glossary`) |

Per-screen "What to do here" links:
- Dashboard → `how-it-works`
- Library → `upload-a-batch`
- Add batch → `upload-a-batch`
- Episode → `review-episodes`
- Schedule → `schedule`
- Schedule approval panel → `approve-a-schedule`
- Next batch → `next-batch`
- Settings/Update → `update-the-pi`
- Activity/Health → `health`
- Activation → `activation`
- History → `health`
