# StudioZero UI redesign — local implementation handoff

Updated 2026-11-13. The local redesign is implemented in the canonical React app and stdlib backend. No deployment, Pi changes, project registration, paid generation or publishing-contract changes were made. The original design reference and requirements remain below.

Start a new implementation session using [BUILD_STUDIOZERO_UI.md](prompts/BUILD_STUDIOZERO_UI.md). Read `AGENTS.md`, the current `docs/STUDIO_PLAN.md` and `docs/PUBLIC_SAFETY.md` first. This document records the current UI direction; older Pi redesign documents describe history and existing behavior, not the new screen design. Project checks and owner approval rules remain authoritative.

## Local implementation status — 2026-11-13

Implemented and independently reviewed locally:

- Studio / Review / Publish shell, four unique project cards, project-scoped batches, compact briefs with examples and optional title/preferences, and preserved operational/deep-link access. Publish separates upcoming work from confirmed published results; uncertain results remain in Operations.
- New private creation records and artifact endpoints in `publisher/app/ui_creation.py`, wired through existing session authentication, mutation guards and write locking in `ui_server.py`. They never invoke engines or publishing. Finalized package import and publishing contracts are unchanged.
- Durable acknowledged briefs, tab-local unsaved drafts, safe retry/recovery after a lost response, project-aware prompts including exact revision mappings, saved research and current feedback, manual clipboard fallback, and real returned files.
- Explicit identity/type/size/hash checks, media probing, atomic immutable revision artifacts, playable current/previous cuts, multi-cut selection and explicit whole-revision approval, supporting-file downloads, failed-replacement preservation, revision/research version conflict checks and approval invalidation.
- Explainers question/angle/sources and hold/accept decisions with local delivery; Marathon owner-reported manual delivery; Originals remains held. None of these UI decisions substitutes for project checkpoints or permission to spend.
- Existing finalized batch import, exact content/caption approval, scheduling drafts, edit/cancel confirmation and unknown-result reconciliation remain on their existing code paths. Scalargame browser preview/export remains available inside its project.

Changed source is primarily `publisher/ui/src/{App.tsx,views.ts,styles.css,api/creation.ts,views/studio/{StudioView,ProjectView,CreationWorkspace}.tsx,views/library/{CreationReviewQueue,LibraryView}.tsx,views/schedule/ScheduleView.tsx,views/ActivityView.tsx}`, the server integration above, targeted tests/E2E and the creation guide. `publisher/docs/CREATION_WORKSPACE.md` documents the external artifact manifest and storage boundaries. `publisher/app/static/`, catalog and motion assets are rebuilt using existing scripts, never hand-edited.

The task started on a heavily modified `main`. The tracked diff/status and prior generated outputs were saved under ignored `library/_dev/ui-redesign-20261113-audit/`; all unrelated existing work was preserved. No Git mutation was performed. The pre-existing catalog expectation was updated for the already-added Dossier style; an existing autopilot CLI test was made deterministic using its fixed test clock. Runtime autopilot behavior was not changed.

### Local preview and repeatable verification

The working fixture lives under `library/_dev/ui-redesign-20261113-fixture/`, with API on loopback port 8876 and Vite on loopback port 5178. The signed-in shared preview uses the built app at `http://127.0.0.1:8876/`; the Vite development preview remains at `http://127.0.0.1:5178/`. Only the task fixture was imported/approved in tests. It remains paused with every channel disabled, no real credentials and no worker socket. Schedule drafts are local proposals; disabled runner channels can still be eligible for drafting under the existing scheduling rules. No schedule was approved or activated.

Use Node 24 and Python 3.12 or newer for this checkout. `library/_dev/ui-redesign-20261113-audit/run-e2e.py` loads the fixture-only environment without printing the passcode and checks that pause/config remain unchanged. It clears schedule-approval and story-worker opt-ins. `verify-http.py` exercises real authenticated MP4 ingestion and revision boundaries. Logs are alongside these ignored helpers. These files are local handoff aids, not portable production configuration.

Verified checks:

- UI typecheck/lint, 354 unit tests across 55 files, production build and generated static/catalog/asset consistency checks. Final narrow review fixes also passed 18 targeted tests.
- Publisher: 532 tests run, all passed with one existing Pi-only ffmpeg-path test skipped. Contracts: 63 passed. Creation tests: 10 independently passed by the reviewer. Public-safety scan: 1,064 files checked, zero findings. Git whitespace check passed.
- Production-bundle Chrome E2E: 15 passed, 5 intentional skips (mobile export, desktop guide and duplicate mutating journey, and both live-worker cases). The fixture remained paused and configuration unchanged. Coverage includes desktop/mobile creation journeys: real MP4 playback, old revision playback, hash rejection without losing approval/media, reordered identical retry, multi-cut approval, feedback, reload, failed save, committed response loss, clipboard denial, research gates and manual delivery.
- Existing finalized-package import/review/draft, keyboard navigation, operational controls and help journeys against isolated fixture state.
- Actual Scalargame browser preview and one-episode export with media checks, using a copy of an existing scratch job bundle. No generation provider or export-upload/finalization opt-in.
- Actual screens inspected; controls and scrolling checked at 320/375/390 px and desktop. Modern Web Guidance `forms`, `accessibility` and `responsive-design` informed native controls/disclosures, error-summary focus, labels, touch targets, container-aware spacing and dynamic viewport media sizing.

### Remaining acceptance boundaries

No physical phone, Safari/Firefox, screen-reader, production performance or provider integration was tested. The final independent code review found no remaining blocking issue; its small Published empty-state finding was corrected. Final bundled E2E also caught and verified the fix for a Help-route crash caused by an unsafe legacy step type cast. Media accessibility depends on actual returned scripts/transcripts; subtitles/audio description are not synthesized or fabricated. The existing large browser-renderer bundle warning remains. Drafts survive reload within the tab; they are not an offline cross-device synchronization service. Selecting a return again is required after a browser reload; partial staged files stay private and the current cut remains intact.

Creative voice/pilot acceptance for Explainers and every project's owner checkpoints remain outstanding project work. External agent handoff stays manual and truthful. No connected-agent progress, publishing registration for Explainers/Marathon, live scheduling, upload deployment or paid automation was added. The next owner step is to try the local preview with a real authorized production; deployment needs separate authorization.

## Owner decisions

- Create and finish videos, then explicitly approve publishing.
- Desktop for creation; phone for reviewing.
- Mostly automatic work; normally review the final cut. This does not waive required project checkpoints.
- Minimal, visual, sequential UI with very little copy and no long default forms.
- Home shows each project once. Batches and episodes belong inside the project.
- For work the app cannot run, provide usable examples and copyable prompts for repo-enabled ChatGPT or Claude Code. Resume inside StudioZero when generated artifacts return.
- A full UI rewrite is acceptable. Reuse working engines, validation and publishing protections; do not reproduce obsolete UI structure just to preserve it.
- Implement locally first, using dispatched agents. Production cutover is a later, separately authorized step.

## Inspect the prototype

Local files are in `library/_dev/ui-prototype/` (ignored by Git, available in this working checkout; not guaranteed in a fresh clone):

- `index.html`: self-contained interactive app; open directly or render inline.
- `layout.html`, `prototype.js`, `prompts.js`, `validation.js`: source and `build.cjs` bundler.
- `README.md`, `INPUTS-AND-STATES.md`, `DIRECTION.md`: interaction notes and earlier reasoning. This handoff takes precedence where the earlier architecture proposal differs.
- `preview-explainers.html`: revised topic-first project view.
- `preview-explainer-research.html`: revised research decision, with no video placeholder.
- `preview-{project,brief,handoff,review,publish,settings}.html`: other sample starting states.

The prototype is a design reference, not production code to paste into React. Do not port its global state, inline event handlers, simulated imports, sample media, invented progress or sample approval records. If ignored files are absent, use this specification and report the missing visual reference; do not claim to have reviewed it.

Run from the repository root:

```sh
node library/_dev/ui-prototype/validation.test.cjs
node library/_dev/ui-prototype/prompts.test.cjs
node library/_dev/ui-prototype/build.cjs
node library/_dev/ui-prototype/journeys.test.cjs
```

Current evidence: validation and prompt checks pass; 22 interaction groups pass, including draft identity, clipboard failure, returned revisions, approvals, manual delivery, settings and schedule recovery. Explainers topic-first copy and research-without-video assertions are included. Rendered desktop and phone-width views were inspected in light/dark themes. This is not production integration, screen-reader, physical-phone or real-import evidence.

## Information architecture

| Destination | Normal screen | Secondary details |
|---|---|---|
| Studio | Four project entries with brief factual status | Settings and Help are utilities, not competing home sections |
| Project | Current videos/batches; start or resume work | Search, completed and archived work in a disclosure |
| Review | Cuts awaiting a decision, with actual media/version | Sources, checks, captions, feedback and revision history |
| Publish | Upcoming / Published; understandable exceptional states | Results, recurring schedule policy and diagnostic detail |

The four entries are Scalargame, Explainers, Marathon and Originals. Recap and series are formats inside Originals. Never duplicate a project because it has two batches. Review counts must identify their unit, e.g. batches versus cuts. Preserve old deep links with route aliases or meaningful redirects.

### Project differences

| Project | Start | Execution | Return/delivery |
|---|---|---|---|
| Scalargame | One short brief with a quiz example; optional overrides | External agent for research/questions/unsupported work; preserve the existing browser preview/export capability | Editable creation artifacts are reviewed separately; finalized batches use the existing validated publisher path |
| Explainers | “What should we explain?”; “Explain a topic”; a short example | Current `/explainer <owner-supplied topic>` workflow; evidence, reframe/no-story and $0 gates | Local cut and delivery artifacts; no active publishing contract or publisher integration |
| Marathon | Week/story notes in the brief; request private inputs only when needed | `/marathon-week`; real footage and facts, no fabricated health data | Manual delivery to the owner's separate accounts; no publisher scheduling |
| Originals | Recap/series choice within one project | On hold; explicit owner authorization and estimate for every paid run | Existing registered contract when authorized; UI design does not lift the hold |

Explainers must not look like a batch manager. Its landing view offers a topic action and shows “Your videos.” Search says “video,” not “batch.” A research problem shows the original question, proposed angle and hold/accept choice. Do not show a video player before a real cut exists. Held/rejected topics must retain evidence and cannot advance through unrelated editing actions. Current voice/pilot acceptance remains unresolved; do not imply a whisper voice or complete production is available. Consult the current Explainers skill and PLAN/SYSTEM; the old weekly patent scout entry point in historical prose is superseded.

## Default journey and input budget

**Project → short brief → make here or agent handoff → return artifacts → review → delivery approval.**

1. Brief: one required “What should we make?” field, an example and “Use example.” Save/resume without duplicate production creation. Working title and creative preferences are optional and collapsed. Originals may expose its format selector. Dates, counts and other detailed controls should appear only when needed for the chosen supported path; do not reproduce the long old prompt-builder form by default.
2. Handoff: a complete copyable prompt, full text behind a disclosure, honest “Waiting for files” status. Plain chat can draft but cannot run repository tools. Clipboard failure must leave a manual-copy path. Copying is neither job submission nor evidence of progress.
3. Prompt: carry the exact brief and explicit preferences; reference the current project skill, mandatory checks, approval/spend limits, required output files and stable production identity. A revision prompt targets the existing batch/episode/revision and current feedback, not a new unrelated brief. Never silently finalize, publish, commit or pay.
4. Return: attach generated output to the correct production and explicit revision. Show missing/mismatched artifacts with a specific recovery action. Do not infer identity from a display title or filename alone. Keep the old playable revision until replacement validation succeeds.
5. Review: real poster/video first, one next decision, obvious version and scope. Multi-episode productions get an episode strip; a single video does not. Optional timed feedback, script/look controls, evidence and credits live below or behind disclosures. A new cut invalidates affected approvals; history and prior artifacts remain.
6. Delivery: cut approval, exact captions/credits/destinations approval, finalization/transfer where required, and scheduling are distinct decisions. Reveal the next controls sequentially. A local cut approval never writes `READY_FOR_UPLOAD` or fabricates publisher approval. Manual/local projects never get generic auto-publish controls.
7. Publishing recovery: edit/cancel requires confirmation; old slots remain until confirmed. An unknown result is reconciled, never automatically resent. Existing schedules do not silently change when creative work changes.

## Visual and responsive requirements

- Quiet typography, restrained project imagery, generous but purposeful spacing, minimal borders and concise labels. Meaningful preview artifacts replace technical tables as the main visual.
- Reuse existing design tokens in the React app. Keep the host-transparent outer canvas only for the embedded HTML prototype; it is not a production-app requirement.
- Use component/container-based responsive layouts. Desktop review can have artifact and decision columns; phone stacks them with readable controls and normal scrolling. Do not compress a desktop grid into a phone.
- At 320/375/390 pixels, controls and long topic titles remain reachable without page-level horizontal scrolling. At desktop widths, avoid full-height empty poster panels next to tiny decisions.
- Visible labels, focus states, keyboard-operable disclosures/dialogs, usable touch targets and reduced-motion support. Errors preserve input and focus the relevant field. Balance short headings only; default wrapping remains the fallback.
- Native video controls and actual media replace the prototype SVG study. No demo scenario picker, “Advance demo,” fixture success indicators or sample analytics in the real product.
- Settings contain device/account status, preferences, budgets and protected operations. Preserve access to operational capabilities; do not fill Home with them.

## Canonical source map

Paths below are relative to `publisher/ui/src/` unless marked otherwise.

| Capability | Reuse/inspect |
|---|---|
| Shell, navigation, tokens | `App.tsx`, `views.ts`, `components/AppNav.tsx`, `styles.css` |
| Catalog and project overview | `views/studio/StudioView.tsx`, `lib/studio.ts`, `lib/catalog.ts`, `api/types.ts`; root `studio.json`, `tools/export-catalog.mjs` |
| Briefs and prompt generation | `views/MakeBatchView.tsx`, `views/studio/PromptBuilderForm.tsx`, `views/studio/PlanMakeContent.tsx`, `lib/promptBuilder.ts` |
| Real Scalargame browser rendering | `views/studio/ExportView.tsx`, `motion/engine.tsx`, `motion/bundle.ts`, `motion/store.ts`, `motion/exportState.ts`, `motion/webPackage.ts`; root `engines/motion/pipeline/web-jobs.mjs` |
| Finalized publishing import | `views/library/AddBatchFlow.tsx`, `lib/batchFolder.ts`, `lib/dropFolder.ts`, `lib/uploadPlan.ts`, `api/client.ts`; root `publisher/app/ui_library.py` |
| Episode review and approval | `views/library/EpisodeDetailView.tsx`, `FeedbackEditor.tsx`, `ContentActions.tsx` in the same directory; root `publisher/app/ui_library.py` |
| Scheduling/history | `views/schedule/` and `api/client.ts`; root `publisher/app/ui_schedule.py`, `ui_approval.py`, `ui_activity.py` |
| Story worker | `views/studio/Story*View.tsx`; root `publisher/app/studio_proxy.py`, `engines/story/src/agent.py` |
| App server/auth | root `publisher/app/ui_server.py` and existing API client/auth modules |

Generated files: `publisher/app/static/`, `publisher/catalog.json` and motion asset manifests. Rebuild with existing scripts when appropriate; never hand-edit. The working tree already contains substantial unrelated changes, including UI source, generated assets and Explainers work. Record the baseline and preserve it.

## Critical integration boundary

The current `AddBatchFlow` imports a finalized publishing batch with `batch.json` and matching `READY_FOR_UPLOAD`. Backend checks enforce project contracts, file hashes and episode/revision identity. It is not an importer for editable pre-final cuts.

Build the smallest separate creation-workspace/artifact path needed for drafts and revisions. Do not loosen the existing finalized importer, amend the publishing contract without approval, or auto-finalize to make the new screen work. Reuse existing persistence and API patterns where suitable; browser checklist state (`lib/makeChecklist.ts`) is not a durable job record or evidence of passed checks.

A workspace record needs stable project/production identity, exact external batch/episode mapping when known, artifact revisions, validation provenance, feedback, next action and decisions tied to those revisions. Use typed, explicit states; server acknowledgement is required for authoritative approval and scheduling. Browser drafts may survive offline with a visible unsynced state. Retrying an import/job must not duplicate it, and failed replacement must preserve the prior revision.

Media/file ingestion must validate paths, sizes, types, required files and identity; reject traversal and unsafe references using existing utilities when possible. Keep raw private health/footage inputs local. A display card for Explainers must not register it as a publishable project. A manual delivery record is distinct from platform confirmation.

## Local build sequence

1. **Baseline and shell.** Read the code and existing tests, document dirty-tree ownership, and redesign the existing React/strict-TypeScript/Vite app. Keep APIs/auth and legacy route access working. Establish Studio / Review / Publish and four unique project entries.
2. **First complete creation slice.** Add durable local briefs, tailored prompt examples/copy, external waiting state, and explicit artifact-return identity. Connect a separate unfinished-cut workspace path. Review a real local fixture video, request a revision, import its replacement and preserve history. This is a real local implementation, not another mock-only page.
3. **Publishing slice.** Connect the new screens to existing finalized-batch import, episode review, hash-bound approval and schedule-draft behavior using isolated fixture state. Keep finalization and publisher admission boundaries explicit. Preserve optional Scalargame browser export.
4. **Project-specific behavior.** Add Explainers topic/research/local-delivery and Marathon private/manual paths. Show Originals' hold honestly. Do not change current project gates to make automation appear complete.
5. **Complete and verify.** Integrate captions, schedule edit/cancel/reconciliation, results, settings and recovery; keep deeper existing operations reachable while migrating. Test desktop and mobile journeys. Build/check generated outputs locally only after source is ready, accounting for pre-existing generated changes.

Proceed through useful local work without requesting routine implementation decisions. If a dependency, contract change or real creative approval becomes necessary, isolate the blocked part, state the specific boundary and continue independent authorized work.

## Agent dispatch

The root coordinates architecture, scope, integration and final review. Use native agent tools or the host's required delegation mechanism; no shell-spawned agents, new branches or worktrees.

- Dispatch a read-only explorer for canonical routes/API/state mapping and migration hazards.
- Delegate one coherent implementation-and-targeted-testing slice to a worker with explicit file ownership. For an Astra root, honor the standing Luna/medium implementation workflow using an available supported tool; report unavailability instead of silently substituting.
- While the writer runs, the root works on acceptance/integration planning; use an independent read-only reviewer for correctness, mobile UX and approval boundaries when the slice is ready.
- Use one writer by default. Additional writers require genuinely disjoint files and agreed interfaces; do not have multiple agents edit `App.tsx`, shared API/types, CSS or generated bundles concurrently.
- Tell every worker that the workspace is shared, other edits must be preserved, and it must not spawn further agents or mutate Git/deploy/provider state. Require changed-file lists, verification evidence and unresolved issues. Root owns generated builds and final acceptance.

## Verification and acceptance

Use the existing packages; no new dependencies are authorized. The local fixture entry points are `publisher/tests/ui_fixture_state.py`, `.claude/launch.json`'s publisher UI development entry, `publisher/ui/vite.config.ts` and `publisher/ui/playwright.config.ts`. Inspect their current options before running: fixture creation can reset its output directory, so use a new task-specific ignored directory rather than overwriting existing state. Keep fixture state paused, all channels disabled, no real credentials and no real worker/publisher process. Ensure `SCALAR_UI_API` and `SCALAR_UI_URL` refer only to the isolated local server, never the Pi. The Playwright config expects a running server; it does not create one.

Targeted tests first, then the affected existing suites:

```sh
# From publisher/ui
npm run typecheck
npm run lint
npm test
npm run build
# Against the isolated local fixture server, when ready
npm run e2e
# Bundle-readiness phase only
npm run build:static
npm run check:static

# From repository root, when backend paths are affected
python3 -m unittest discover -s publisher/tests -p 'test_*.py'
python3 -m unittest discover -s contract/tests -p 'test_*.py'
```

Acceptance must include: one project per home tile; compact forms/examples; draft reload/resume; clipboard denial; same-production return; wrong identity/hash rejection; failed replacement preservation; current-version playback/feedback; approval invalidation; no automatic finalization; finalized batch compatibility; manual/nonregistered projects blocked from scheduling; schedule edit/cancel and unknown-result recovery; offline state; keyboard access and reachable controls at phone widths. Existing unaffected deep links and operational access must remain usable.

Report baseline failures separately from regressions. An independent agent reviews significant changes; root verifies and fixes concrete findings. Do not claim an integration is complete based only on mocked UI tests, or a physical device is tested based on a resized browser.

## Authorization limits

Local implementation only. Do not create/switch branches or worktrees, stage, commit, push, open PRs, deploy, update the Pi, mutate live schedules or library state, start generation, install dependencies, create accounts or incur charges. Do not alter finalized batches or frozen sources. No publisher contract/project-registration change without owner approval. Do not log or include credentials, private addresses or raw health data in prompts/docs. These restrictions also apply to delegated agents.

A useful final handoff includes a working local preview, exact commands, changed files, checks and remaining blockers. Deployment remains a separate decision.
