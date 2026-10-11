# Pi UI redesign plan — clean pass

Status: **built 8–9 October 2026** (phases 1–8 of §8, in order, in the main checkout; not yet committed or deployed). Where the build differs from this plan is listed in §11. Operator guide for the current UI: [publisher/docs/PI_UI.md](../publisher/docs/PI_UI.md). Backend contracts do not change except where §7 says so.

Goal: the same safety model (approval of record, finite approved manifests, owner-only activation) with a UI that a tired person on a phone can use without reading the guide. Fewer sections, fewer fields on screen, one obvious action per screen.

## 0. The journey is the UI

The marketing plan is one repeating loop: make videos on the Mac, upload them, approve them, schedule them, let the Pi post, learn from the results, make the next batch. The UI's job is to show where the owner is in that loop and what the one next action is. Everything else is reference.

Six steps, one vocabulary, used identically in the Home strip, screen titles, the Next step card, Activity kinds, empty states and guide anchors:

| # | Step | Where it happens | Screen | Live state the Pi knows | The one action |
|---|---|---|---|---|---|
| 1 | **Make** | Mac (`/video-batch`) | Library › Make a batch | next batch id, open feedback, last brief/retro, whether the batch has arrived | Copy prompt (then follow the checklist) |
| 2 | **Upload** | Pi UI | Library | batch present, files verified/missing | Drop the folder |
| 3 | **Review** | Pi UI | Library › episode | episodes awaiting review, approved | Approve |
| 4 | **Schedule** | Pi UI | Schedule | approved schedule, runway days, draft | Generate, then type APPROVE |
| 5 | **Post** | Pi (publisher) | Activity, Settings › Activation | paused/running, next posts, uncertain jobs | Run the activation command (owner, once) |
| 6 | **Learn** | Pi UI → Mac | Library › Make a batch (step 1) | posted permalinks, performance, open feedback | Download feedback.json |

Step 6 feeds step 1 of the next batch, so the strip is drawn as a loop, not a line.

Cohesion rules (apply to every screen):

1. **One progress model.** Step state is `todo / current / done / blocked` and comes from `src/lib/journey.ts`, a pure function of the dashboard payload (plus the browser-local Make checklist). Home, the Next step card, screen headers and empty states all read it; nothing computes progress on its own.
2. **One primary action per screen**, and it is always the current step's action. Secondary actions are plain buttons or live under ⋯.
3. **Every screen says which step it is.** Under the `h1`: "Step 3 of 6 · Review". The tab bar is for jumping, the step line is for orientation.
4. **Empty states point backwards.** An empty Library says "Nothing to review yet. Make a batch →". An empty Schedule says "Approve episodes first →". An empty Activity says "Nothing has been posted. Activation is the owner's command →".
5. **Mac steps are shown, not hidden.** Anything that happens off the Pi is a numbered instruction with a Copy button, in the same visual style as the live steps, labelled "on the Mac".
6. **No duplicate surfaces.** A fact (count, status, next post) appears in one place plus the Home strip. Diagnostics live in Settings › System only.
7. **Same words everywhere.** Step names, badge labels (`labels.ts`) and guide anchors share the vocabulary above; "History", "Dashboard", "Next batch", "Activation" disappear as screen names.

## 1. Locked decisions

| # | Decision |
|---|---|
| D1 | Five sections: **Home, Library, Schedule, Activity, Settings**. History merges into Activity. Activation, Update, Backup, Timers, Health/budgets/storage and Session merge into Settings. Next batch becomes **Make a batch**, the first step of the Library funnel (§4.7), and the funnel strip on Home. Guide becomes a help icon in the header; every screen keeps its "What to do here" panel. |
| D2 | Phone single-video upload (`PhoneUploadFlow`, `ManualMetadataForm`, backend `post_manual_video`/`post_manual`, `ui_library.stage_manual_video`/`create_manual_batch`) is **removed**. Mac batches are the only way in. The `legacy-2026-10-05` batch stays readable. |
| D3 | Schedule is **preset-first**: the recommended 21-day plan from branch `social-metrics` is the default path; the per-platform controls sit behind one "Customize" disclosure. Step one of the build is merging `social-metrics` into `main` and rebuilding the static bundle. |
| D4 | Mobile: bottom tab bar (5 tabs, 56 px, safe-area aware). Desktop from 1024 px: fixed 220 px left sidebar. Same five items, same order, same icons. |
| D5 | Visual language stays: system font, one accent, light/dark via `prefers-color-scheme`, no inline styles (CSP). This pass standardizes spacing, cards, badges and buttons; it does not add a design library or fonts. |
| D6 | Draft preview, the typed `APPROVE <hash>` phrase, the pause control, the activation command and reconciliation stay exactly as they are. Simplification never touches the safety steps. |
| D8 | The UI shows the **whole funnel end to end**, including the Mac-side video generation it cannot run: Make → Upload → Review → Schedule → Posting → Learn. Mac steps are shown as numbered instructions with copyable commands and a local checklist; Pi steps are live. The step state is derived from Pi data wherever possible (a batch id appearing in the library completes Make), and from a browser-local checklist only for the Mac checkpoints. No new backend state. |
| D9 | Home is the journey. The six-step loop with the current step expanded is the first and largest element; `journey.ts` is the single source of step state (§0). |
| D7 | Plan only in this session. The build follows the phases in §8 in order; each phase leaves `npm run typecheck && npm run lint && npm test && npm run build` green and the e2e nav helper updated. |

## 2. Information architecture

```
Home        one next step · funnel strip (6 steps) · pipeline counts · attention list · platforms
Library     make a batch (Mac instructions + brief) · batches (drop zone) · episode list · episode review
Schedule    approved schedule & queue · new draft (preset-first) · draft preview · approval
Activity    one timeline · filter chips · search · job detail · export (menu)
Settings    publishing control · activation · update · backup · system (timers, health, storage) · session
?           guide (help icon, top right; opens #/guide/<anchor for current screen>)
```

Hash routes (all existing deep links keep working through redirects):

| Old | New |
|---|---|
| `#/dashboard` | `#/home` (`#/dashboard` redirects) |
| `#/history` | `#/activity?tab=posts` |
| `#/activation` | `#/settings#activation` |
| `#/next-batch` | `#/library/make` |
| `#/library/episode/<id>/<rev>` | unchanged |
| `#/guide/<anchor>` | unchanged |

## 3. Shell and navigation

**Mobile (375 px)**

```
┌──────────────────────────────┐
│ Scalar publishing        (?) │  header: brand + help icon, 48 px
├──────────────────────────────┤
│                              │
│  <screen content, 16 px      │
│   gutters, cards stacked>    │
│                              │
├──────────────────────────────┤
│  ⌂     ▣     ▦     ≡     ⚙  │  tab bar 56 px + safe area
│ Home  Lib  Sched  Act  Set   │  active = accent text + 2 px top bar
└──────────────────────────────┘
```

**Desktop (≥ 1024 px)**

```
┌───────────┬──────────────────────────────────────────────┐
│ Scalar    │  Screen title                            (?)  │
│ publishing│                                               │
│           │  ┌──────────────────┐ ┌───────────────────┐  │
│ ⌂ Home    │  │ primary column   │ │ secondary column  │  │
│ ▣ Library │  │ (max 720 px)     │ │ (360 px, sticky)  │  │
│ ▦ Schedule│  └──────────────────┘ └───────────────────┘  │
│ ≡ Activity│                                               │
│ ⚙ Settings│                                               │
│           │                                               │
│ Signed in │                                               │
│ v abc1234 │  (installed commit, from Settings → Update)   │
└───────────┴──────────────────────────────────────────────┘
```

Rules: one `h1` per screen, focus moves to it on navigation (as today). The auto-refresh bar (30 s, pause toggle) becomes a small "Updated 12 s ago · ⏸" line under the title on Home and Activity only. The offline/unauthorized notices keep their current behaviour.

## 4. Screens

### 4.1 Home (replaces Dashboard's nine cards)

```
Your loop                                   [the journey card; first thing on the screen]
 ① Make ✓ · ② Upload ✓ · ③ Review ● · ④ Schedule · ⑤ Post · ⑥ Learn ↺   (strip; phone scrolls it)
 ┌────────────────────────────────────────┐
 │ Step 3 · Review                        │   the current step expanded (the old "Next step" hero,
 │ 4 episodes from 2026-10-b01 to review  │   now inside the loop so the hero and the strip never
 │ Watch each one, leave feedback,        │   disagree)
 │ approve the ready ones.                │
 │                      [ Review 4 → ]    │   one primary button
 └────────────────────────────────────────┘
 Done steps show their fact in one line when tapped (e.g. ② "24 files · 2026-10-b01 · 2 Oct").
 Blocked steps say why and who (e.g. ⑤ "Paused · owner command, see Settings").

Attention                                   [only rendered when non-empty]
 ⚠ Threads token expires in 3 days           → Settings
 ⚠ Job ig-0007 uncertain, needs reconciling  → Settings › Activation (owner command)
 ✕ Instagram: last post failed (quota)       → Activity

Platforms                                   [one row per platform, three dots]
 Instagram   ● ● ●   enabled                 dots = posting test · authenticated · recurring
 Threads     ● ● ○   token renewal due       (good/bad/warn tones; legend once at the bottom)
 Bluesky     ● ● ●
 Facebook    ● ○ ○   not authenticated
 YouTube     ○ ○ ○   not set up
 X           ● ● ○   via Buffer
 TikTok      ○ ○ ○   no API route

```

The Pipeline counts card is dropped: the strip carries the counts (done steps show them on tap, the current step in its hero).

Moved out of Home: Pipeline counts → the loop strip, Next batch → Library › Make a batch, Publishing control → Settings (top), Approved schedule → Schedule, Timers / Health / budgets / storage → Settings › System, Issues + Jobs needing reconciliation → merged into Attention (full detail still in Settings › System and Activity).

`nextStep.ts` becomes the current-step rule inside `journey.ts` (same priorities, same tests, one more input: the Make checklist). The three platform tri-states collapse into one row by reusing `triTone`.

### 4.2 Library

List screen:

```
[ + Make a batch ]  (secondary button, top; opens §4.7. Becomes the primary button when there is nothing to review)
[ Drop a batch folder here, or Choose folder ]      (drop zone, full width, only when nothing is uploading)
Upload progress: 14 of 24 files · 312 MB · 1 failed [Retry]   (only while active)

Batches                                              (chips, horizontally scrollable on phone)
 (All) (2026-10-b01 · 8) (2026-10-pilots · 8) (legacy · 8)

Filter  (To review ●4) (Approved) (All)              (segmented control, default = To review)

┌──────────────────────────────────────┐
│ [cover]  Which country has…          │   one card per episode:
│          Countries · hard · rev 2    │   cover thumb, question, 3 facts, status badge,
│          Ready for review            │   tap anywhere → review screen
└──────────────────────────────────────┘
```

Removed from the list: per-card expanders (eligibility, captions, duplicate history, approvals), per-card Approve/Withdraw/Delete buttons, the "Filter and review" heading. "Approve all shown" moves to a sticky bottom bar that appears only when the To review filter is active and ≥ 2 episodes are shown. Batch notes (BRIEF/RETRO) move to the episode review screen and Settings › Next batch.

Episode review screen (`#/library/episode/<id>/<rev>`), phone:

```
← Library                              3 of 4
[         video player, 9:16, muted     ]
Which country has the most time zones?
Countries · hard · 42 s · rev 2 · batch 2026-10-b01

[ Approve ]        [ Feedback ]        [ Next → ]      (sticky bottom bar, 44 px targets)

▸ Posts and captions (per platform)
▸ Answer and evidence            (Reveal answer stays a button inside)
▸ Platform eligibility
▸ Measured on the Pi
▸ Batch notes (BRIEF / RETRO)
▸ History (approvals, duplicates, ledger records)
▸ More actions: Withdraw · Delete
```

Desktop: episode list on the left (360 px), review on the right; Next/Previous move through the current filter. Feedback opens the existing `FeedbackEditor` in a bottom sheet (phone) or the secondary column (desktop). Approve keeps the existing confirmation and records the same reviewer/hash fields.

### 4.3 Schedule

```
Approved schedule                       [card; replaces the Dashboard card + QueueList header]
 21 days · 2026-10-09 → 2026-10-29 · hash 3f9a12c0 · approved 7 Oct 21:40
 Next: Threads tomorrow 09:00 · X 09:30 · Bluesky 10:30
                                              [ View queue (18) ]

New draft
 Start date  [ 2026-10-09 ]        Timezone  America/New_York  (change)
 Recommended plan: one post per platform per day for 21 days.
 Threads 09:00 · X 09:30 · Bluesky 10:30 · Facebook 12:15 · YouTube 16:00 · Instagram 18:00 · TikTok 19:00
 Blocked today: TikTok (no route) · Facebook (not authenticated)
 ▸ Customize                             (disclosure; opens the existing GeneratorForm fieldsets,
                                          already filled with the preset values)
                                              [ Generate draft ]

Draft 7c21…  (after generate)
 18 of 21 requested slots fillable · 2 warnings
 [ list grouped by day, each row: time · platform · video · ▸ caption ]
 Edit / remove a row → new draft (as today)

Approve
 Type APPROVE 7c21e0a4 to deploy media and record this schedule. Nothing is published.
 [ APPROVE ________ ]  [ Approve schedule ]
```

Desktop: draft list left, approval panel sticky right (as today). The form still starts empty in state terms: the preset values are shown as the proposal and only become form state when Generate or Customize is tapped (keeps the locked "preset applies only on tap" rule in spirit; the generate hash is identical either way).

Queue (`View queue`): the current `QueueList` with cancel/edit, as a sub-screen `#/schedule/queue`.

### 4.4 Activity (absorbs History)

```
(All) (Posts) (Uploads) (Approvals) (System)      filter chips, single select
[ Search question id, job id, platform… ]  (⋯ menu: Platform ▾, Status ▾, Dates, Export CSV, Export JSON)

Today
 18:02  ✓ Instagram published  ep12 "Which country…"  → link
 16:00  ✓ YouTube published    ep11                    → link
 09:31  ⚠ X accepted, awaiting confirmation  ep10
Yesterday
 21:40  ◆ Schedule 3f9a12c0 approved (18 jobs)
 20:12  ↑ Batch 2026-10-b01 uploaded (24 files)
 …
[ Load older ]
```

The Posts chip is the old History: same `/api/history` query, rendered as the same timeline rows plus a desktop table toggle. Job detail stays the existing modal. The seven History inputs and three Activity selects collapse into the search box plus the ⋯ menu; the default view has zero visible form fields.

### 4.5 Settings (one scrollable page, anchored sections, desktop gets a section index on the left)

```
Publishing control    Paused / Running · [ Pause publishing ] (danger, confirm as today)
Activation            readiness checklist · owner command with Copy (ActivationView, unchanged)
Update                installed vs latest · [ Check for updates ] · What's new · [ Update ] (UpdateSection, unchanged)
System                timers · monitor · budgets · storage · issues list (from the old Dashboard cards, collapsed by default)
Backup                [ Download backup ]
Session               signed in since · [ Sign out ] · change passcode note
```

### 4.6 Guide

Unchanged content and renderer. Entry points: the header help icon (opens the anchor for the current screen, `meta.json` gains a `screen → anchor` map) and the per-screen "What to do here" panel, which becomes a single collapsed line under the title ("What to do here ▸") instead of a card.

### 4.7 Make a batch (`#/library/make`) — the Mac step, shown in the UI

The UI cannot render videos, but it is where the owner starts and where they come back, so it carries the instructions. One screen, one numbered list, nothing hidden:

```
← Library                       Make a batch  2026-10-b02

Step 1 · Carry feedback over                 (Pi, live)
 3 open feedback notes · last retro 2 Oct · last brief 1 Oct
 ▸ Read the open feedback          (collapsed list from /api/next-batch)
 [ Download feedback-2026-10-b02.json ]  → put it in marketing/library/_inbox/ on the Mac

Step 2 · Write the brief                     (Pi, live; the existing editable brief)
 [ brief textarea, prefilled from the last brief + open feedback tags ]
 [ Copy prompt for Claude ]  → paste into Claude Code opened in scalargame/marketing

Step 3 · Let Claude make it (on the Mac)     (instructions + local checklist)
 Claude runs /video-batch brief 2026-10-b02 and stops at each checkpoint for your OK:
 ☐ Checkpoint 0  brief and open questions
 ☐ Checkpoint 1  questions, answers, choices, difficulty
 ☐ Checkpoint 2  pilot video per game (only if the brief asks)
 ☐ Checkpoint 3  review/index.html, covers.png, checkpoint3.md
 ☐ Finalize      say "finalize" → READY_FOR_UPLOAD is written; the folder is frozen
 Expect about N minutes of rendering per video on the Mac.   (static text from the guide)
 Something off? Ask Claude for a revision before finalizing; after finalizing, make a new batch.

Step 4 · Upload here                         (Pi, live)
 [ Drop library/2026-10-b02/ here, or Choose folder ]   (same drop zone as the Library list)
 → after upload: "Review 8 episodes" link

Step 5 · Retro (after posting)               (instruction)
 Run /video-batch retro 2026-10-b02 on the Mac; the retro shows up here as batch notes.
 [ Mark feedback as used ]     (existing action)
```

State rules:
- Steps 1, 2, 4 read and write the existing `/api/next-batch`, brief and upload endpoints; no new backend.
- Step 3's checkboxes are a per-batch-id browser-local checklist (`localStorage` `scalar-make-<batchId>`), purely a memory aid; it is cleared and the whole step is marked done automatically once a batch with that id exists in the library.
- `journey.ts` derives the strip: Make = next batch id not yet in library (current once the brief was edited or feedback downloaded in this browser); Upload = last batch has `awaiting_files`; Review = `awaitingReview > 0`; Schedule = no approved schedule covering the next 14 days; Post = blocked while paused, current while running with N next; Learn = open feedback or a retro newer than the last brief. The current-step rule keeps `nextStep.ts`'s priorities and gains "Finalize and upload 2026-10-b02" when the Make checklist is complete but the batch has not arrived.
- Desktop: steps 1–2 left column, steps 3–5 right column.
- Guide `make-a-batch.md` stays the long form; this screen links to its anchors from each step.

## 5. Components and tokens

Keep `styles.css` as the only stylesheet. Reduce to one of each:

| Piece | Rule |
|---|---|
| Card | `--surface`, 1 px `--border`, `--radius` 8, padding 16, gap 12 between cards. No nested cards. |
| Badge | `StatusBadge` only; tones `good / warn / bad / info / neutral` from `labels.ts`. No other coloured text. |
| Buttons | `btn` (secondary), `btn-primary` (one per screen), `btn-danger` (Pause, Delete). Min 44 px tall on touch. |
| Chips | New `Chip` (filter, single/multi select, `aria-pressed`). Replaces selects for platform/kind/status filters. |
| Disclosure | Native `<details>` with one `summary` style; used for every "more" section. |
| Sticky action bar | New `ActionBar` (bottom on phone, inline on desktop) for Approve/Feedback/Next and Approve all shown. |
| Bottom sheet | `Modal` gains a `sheet` variant (slides from the bottom on phone, centred on desktop). |
| Tab bar / sidebar | New `AppNav` rendering both layouts from `VIEWS`. |
| Spacing | 16 px gutters, 12 px card gap, 8 px inside rows. Type: 16 body, 14 secondary, 20/24 titles. |

Delete: `ManualMetadataForm`, `PhoneUploadFlow`, `TextCounterField` (only used by the manual form), the three platform status cards, `HistoryView` (folded into Activity), `AutoRefreshBar` (replaced by the one-line status).

## 6. What the user sees less of

- Dashboard: 9 cards → 4 cards plus a conditional Attention list.
- Schedule: 24 visible inputs → 2 (start date, timezone), the rest behind Customize.
- Library list: 5 expanders and 3 buttons per card → 0; one tap opens review.
- History + Activity: 10 form controls → 1 search box and a chip row.
- Navigation: 9 links wrapping to 3 rows → 5 fixed tabs.
- Phone upload: 48 fields → removed.

## 7. Backend changes (small, in `publisher/app`)

- Remove `post_manual_video`, `post_manual`, `ui_library.stage_manual_video`, `ui_library.create_manual_batch`, `ui_views.manual_*` and their tests. Keep the manual-batch rows readable so `legacy-2026-10-05` still lists.
- `GET /api/dashboard`: no schema change. The UI derives the Pipeline counts from `standing` plus the existing library/schedule summaries; add `postedLast7Days` to `standing` if it is not already derivable (one query on the ledger).
- `GET /api/activity` and `/api/history` unchanged; the Posts chip calls `/api/history`.
- Guide `meta.json`: add `screens: { home, library, episode, schedule, activity, settings }` → anchor.

## 8. Build order (one PR per phase, each green on typecheck, lint, Vitest, build, `check:static`)

1. **Merge `social-metrics` into `main`.** Resolve the static bundle by rebuilding (`npm run build:static`), not by hand. Run the publisher unittests and the UI suite. Owner then runs `deploy/enable-metrics.sh` on the Pi when ready (outside this plan).
2. **Shell and journey:** `journey.ts` (pure, tested against fixture payloads for every step state), step line under each `h1`, `AppNav` (tab bar + sidebar), route table with redirects, help icon, `views.ts` down to five ids, e2e `smoke.spec.ts` nav helper updated to the tab bar role (`navigation` named "Sections" stays).
3. **Settings:** move Publishing control, Activation, Update, Next batch, System, Backup, Session into `SettingsView` sections. Delete the old routes.
4. **Home:** rebuild `DashboardView` as §4.1 around the loop card. Tests: `DashboardView.test.tsx` and `nextStep.test.ts` keep passing; add the Attention and Platforms row tests.
5. **Activity + History merge:** chips, search, ⋯ menu, Posts chip, desktop table toggle. Move `HistoryView` tests to Activity.
6. **Library:** Make a batch screen (§4.7) from `NextBatchView` pieces, funnel strip on Home, `nextStep` extension; remove phone upload (UI + backend + tests), chip filters, single-tap cards, review screen with `ActionBar`, Next/Previous, bottom-sheet feedback, desktop two-column.
7. **Schedule:** preset-first form, Customize disclosure, approved-schedule card, queue sub-route. `scheduleForm.test.ts` and `GeneratorForm.test.tsx` extended for "preset shown but form state empty until tap".
8. **Polish:** token sweep of `styles.css`, delete dead components, Playwright mobile smoke (install browsers on the Mac first), guide screen map, `PI_UI.md` §9 Layout and §"Rebuild screens" rewritten, this file marked built.

## 9. Acceptance

- Phone 375×812: no horizontal scroll on any screen; every primary action reachable without scrolling past one screen height on Home, episode review and Schedule approval.
- Desktop 1280: Library and Schedule use two columns; nothing wider than 1120 px.
- Keyboard: tab order follows visual order; focus lands on `h1` after navigation; `details`/chips/tab bar operable with keyboard; axe has no serious violations (Playwright `@axe-core/playwright`).
- Dark mode renders every badge tone with ≥ 4.5:1 contrast (check once with the existing tokens).
- Same hashes: generating a draft from the preset in the new UI yields the same draft hash as filling the old form with the preset values.
- All existing guide anchors and in-guide links still resolve (`guide.test.ts`).
- A first-time owner can go from an empty Pi to a scheduled batch using only the screens, never the guide: Home → Make a batch → (Mac) → Upload → Review → Schedule → Approve → Settings › Activation command. Checked by the Playwright smoke in phase 8 against fixture state.

## 10. Not in scope

Fonts, icon library, animation beyond the sheet slide, new backend features, metrics charts (the `social-metrics` data is only shown as the existing Performance text on Settings › Next batch), any change to approval, manifest, activation or reconciliation semantics.

## 11. Build notes (where the build differs, and why)

- **`standing` gained five read-only fields** (`nextBatchId`, `lastBatch.awaitingFiles`, `postedLast7Days`, `lastBriefAt`, `lastRetroAt`; documented in `docs/REBUILD_CONTRACTS.md` §2). §7 allowed only `postedLast7Days`, but Upload (files missing), Make (the next id) and Learn (retro newer than brief) are not derivable from the old payload. No new stored state.
- **`TextCounterField` stays**: §5 says only the manual form used it, but `FeedbackEditor`, `DraftPreview` and `QueueList` use it too.
- **No axe run**: `@axe-core/playwright` would be a new dependency. Instead `e2e/keyboard.spec.ts` checks focus on the title, tab order into the content, chips (Space) and disclosures (Enter), and `src/styles.contrast.test.ts` checks every badge tone and the accent button at ≥ 4.5:1 in light and dark.
- **`nextStep.ts` is kept** as a small adapter over `journey.ts`'s `currentFocus`; its tests keep the same cases in the same priority order with the new step names and routes (`library/make`, `settings#update`). New rules, in order: Upload when the last batch misses files (after Review), Post blocked while paused, Learn for open feedback or a newer retro; an available update is grouped with Post.
- **Make a batch step 5 carries the batch notes** (BRIEF.md / RETRO.md upload for the last Mac batch), since the Library list no longer has per-batch panels; the review screen shows them read-only behind Reveal answer.
- **The reviewer name moved into the Approve dialog** (remembered on the device) instead of a field on the list.
- **Schedule on phones** adds a sticky "Go to approval ↓" so the approval panel is one tap away after a long draft (§9). The approval itself is unchanged.
- **`meta.json` `screens`** also maps `make`, `queue` and `guide`; Settings sections with their own guide section (activation, update, system) override the page's anchor.
- Browsers: Playwright's Chromium was installed (`npx playwright install chromium`); `SCALAR_UI_BROWSER_CHANNEL=chrome` still works.

