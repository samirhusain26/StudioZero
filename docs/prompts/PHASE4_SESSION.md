# Session prompt: StudioZero, Phase 4 (contract v2 + publisher)

You are continuing a multi-session restructuring of **StudioZero**, the public studio repo behind the @studiozeroflow social accounts. Phases 0–3 are done. This session runs **Phase 4: contract v2 and the publisher**. It is the first behaviour change on the Pi's publishing path:
- the v2 batch contract (one project per batch, `contentId`, `render`, credits, disclosure), with v1 valid forever;
- the Pi importer for v2;
- per-project duplicate protection;
- mix policy in the schedule draft and the autopilot;
- AI disclosure labels per platform;
- credits and attribution in the text that posts (TMDB notice included);
- project, engine, format and renderer in the UI and in Learn.

Don't re-derive or re-argue earlier decisions. Contract v2 (plan §5) was approved at CHECKPOINT 1 (plan §9; the "still open" line in §10 predates that approval). Device compute (decision 8) stands: the Pi never renders or encodes.

## Read first

1. `AGENTS.md` (the same as `CLAUDE.md`): tree, commands, hard rules, public-safety rules.
2. `docs/STUDIO_PLAN.md`:
   - the status line and §1 locked decisions;
   - **§5 contract v2** in full (5.1 batch, 5.2 episode, the attribution rule, AI labels, 5.3 project modules, 5.4 v1 → v2 rules);
   - §9 Phase 3 checklist and the parity list; §15 Phase 3 log (measurements, the browser vs `render.sh` side by side, open owner items).
3. `docs/prompts/STUDIOZERO_CONSOLIDATION.md`: "Phase 4", "Phase 5" and "Standing rules for every phase".
4. The contract: `contract/BATCH_CONTRACT.md` (v1), `contract/library_contract.py` (validate/finalize, the ffprobe re-measure), `contract/tests/`.
5. The packager and engine hand-off: `tools/RENDER_JSON.md`, `tools/render-json-core.mjs`, `tools/package-core.mjs`, `tools/package.mjs`, `projects/scalargame/package-core.mjs` + `package.mjs`, `tools/package-regression.mjs`; the browser packager `publisher/ui/src/motion/webPackage.ts` (it shares the cores, so a v2 packager change reaches browser-made batches too).
6. The publisher: `publisher/app/` (runner, adapters, `approval`, `activation`, `autopilot`, `operations`, `metrics`, `identities.py`, the `ui_*` modules and `ui_library.py`'s import path), `publisher/docs/PUBLISHING_PIPELINE_PLAN.md`, `PLATFORM_MATRIX.md`, `SCHEDULE.md`, `MEASUREMENT.md`, `docs/AUTOPILOT_PLAN.md`.
7. Projects and catalog: `studio.json`, `projects/*/project.json` (mix `share`/`target`, link and call-to-action policy, captions, budget), `publisher/catalog.json` and `publisher/app/ui_catalog.py` (the Pi already reads the catalog).
8. The UI: `publisher/ui/src/api/types.ts`, `views/library/`, `views/schedule/`, `views/ActivityView.tsx`, `lib/postMetrics.ts`, `lib/funnel.ts`, `lib/journey.ts`, `publisher/ui/content/guide/`.
9. Memory: `~/.claude/projects/-Users-samirhusain-Personal-code-projects-StudioZero/memory/MEMORY.md` and `studiozero_consolidation.md`.
10. `git log --oneline -20` and `git status`.

## State at handoff (2026-10-12, verified)

- **In sync:** StudioZero `main` = GitHub = Pi, at the commit that added this prompt or later. `main` has branch protection (no force-push or deletion).
- **The Pi** is a Raspberry Pi Zero 2 W (512 MB, Debian 13, Python 3.13). Units: the UI (`MemoryMax=96M`, `IPAddressDeny=any`), the publisher timers, autopilot (05:15 and 17:15 Pi time), metrics, the apply-units path, and since Phase 3 **`scalar-social-studio-proxy.service`** (DynamicUser, group `scalar-social`, unix socket `/run/scalar-social-studio/proxy.sock` 0660, `IPAddressDeny=any`, `MemoryMax=48M`, about 19 MB RSS). Its worker is **not configured yet** (owner item), so Studio › Story jobs shows "Worker offline".
- **Sparse checkout** on the Pi: `contract/`, `engines/motion/public`, `publisher/` (from `publisher/deploy/sparse-paths`, applied by the updater).
- **Contract:** v1 only. Both finalized 2026-10 batches validate; `node tools/package-regression.mjs` re-packages both byte-identical. Browser-made batches are v1 and byte-identical to the Mac packager's output.
- **Phase 3 delivered:**
  - Studio tab: overview, Make a batch (prompt builder mode 1), New format/style/project (mode 2), Export (in-browser motion preview/export/QA/upload), Story jobs (laptop worker through the Pi proxy);
  - `GET /api/catalog`; motion assets streamed from the Pi (`/api/assets/motion/…`, allowlist `publisher/motion-assets.json`);
  - `render.json` carries `job.renderer` (`render.sh` or `web`);
  - the story worker agent `engines/story/src/agent.py` (B1, B2, B5 fixed; paid runs off unless `STUDIO_AGENT_ALLOW_PAID=1`); the old dashboard is retired;
  - security review `docs/plan/PHASE3_SECURITY_REVIEW.md` (resolved).
- **Story engine:** still open and blocking paid runs: B3 (no series TTS; mixed audio/no-audio concat), the rest of B7/B8, B9, LLM/image/TTS spend not in the ledger, under-counted submit timeouts.
- **Known test debt:** `publisher/ui/e2e/smoke.spec.ts` still asserts the typed schedule-approval phrase retired on 2026-10-09 (`PI_UI.md`); it fails on both projects until updated (owner OK needed: an earlier edit was blocked as a security-test change).
- **Owner decisions still open:** target mix shares per project, the Originals monthly budget (`monthlyUsd: 0` today), a full ffmpeg on the Mac. Owner set-up items: the laptop worker (Tailscale Serve + `agent-token.py --send-to-pi`), Safari 26 and phone export checks.

## Target structure

```
Engines (Mac / browser / laptop worker)          Packager (tools/, shared with the browser)        Pi (publisher/, contract/)
- render.json per episode (models, cost,          - render.json + project captions → batch.json     - validator v1 + v2 (one module, dispatch on
  credits, disclosure, job.renderer)               - v1 for scalargame until the Pi runs v2;          schemaVersion; project modules in
                                                   then v2 per project                               contract/projects/<project>.py)
                                                   - writes required attribution into every          - importer, per-project duplicate key
                                                     platform text that posts                          (contentId; v1 questionId = same key)
                                                                                                     - schedule draft + autopilot honour mix
                                                                                                     - AI labels per platform where supported
                                                                                                     - UI + Learn by project/engine/format/renderer
```

The Pi keeps its invariant: it publishes exactly the approved text with `{link}` expanded and nothing else changed. Attribution is composed by the packager and verified by the validator, never added by the publisher.

## Remaining follow-ups

- Ask the owner the open decisions when they come up (mix targets, Originals budget). Never invent values: until set, mix policy must behave exactly as today for Scalargame-only queues.
- The smoke e2e's typed-phrase assertion (above): ask before changing it.

## Phase scope (behaviour change; ship in small, green steps)

Build in this order. Get each step green, commit and ship it before starting the next. Anything that touches the live publishing path ships alone, after its tests, and is watched through one autopilot run.

### 1. Validator v2 (contract/)
- `contract/library_contract.py` dispatches on `schemaVersion`; the v1 path is unchanged byte for byte. Core v2 rules from §5.1–5.2; project modules `contract/projects/scalargame.py` and `contract/projects/originals.py` (§5.3); the licence list and the attribution rule (TMDB notice whenever a credit has `license: TMDB`).
- Tests: every v1 fixture still passes; both finalized 2026-10 `batch.json` documents validate on every run; v2 fixtures for both projects, including refusals (missing attribution on a posting platform, unknown licence, `aiGenerated` false with a generative model, colliding `contentId` namespace, link rules).
- `contract/BATCH_CONTRACT.md` gains the v2 section. Contract changes need the owner's approval: §5 is approved; ask before any rule beyond it.

### 2. Packager v2
- `tools/package-core.mjs` and the project cores write v2 for a project once the Pi runs the v2 validator; Scalargame keeps v1 until then and the regression stays byte-identical. Originals gets a project core (Phase 5 uses it).
- The browser packager shares the cores: keep browser output equal to the Mac's (byte-identical test).

### 3. Pi importer and duplicate protection
- The import path accepts v2, normalizes v1 episodes as §5.4 says, and keys duplicates on `contentId` (the existing `question_id` column; namespaces cannot collide; no migration). Tests with both versions in one library.

### 4. Mix policy
- The schedule draft and the autopilot fill slots by project share when targets exist; with `target: null` (today) behaviour is exactly as now. Tests for both; the live schedule is never paused or modified by you.

### 5. AI disclosure labels
- Map `disclosure` to each platform's label where the API (or Buffer) supports it; record "not supported" in the job otherwise. Verify each API's field from its current docs (context7 / official docs) before coding; no live test posts without the owner's OK.

### 6. UI and Learn
- Episodes show project, engine, format and renderer (`web` vs `render.sh`); Learn metrics group by them. Library filters by project. Update the guide pages that change.

### Then
- `build:static` + `check:static`; Pi memory check after the import changes; a short security review of the new import and label paths (fix findings); update the guide.

## Verification before Phase 4 counts as done

- `python3 tools/public_safety_check.py`: 0 findings, before every push.
- Publisher and contract suites (new v2, importer, duplicate, mix and label tests); the story smoke test and agent tests at $0.
- UI typecheck, lint, Vitest, e2e, `build:static` + `check:static`.
- Motion `tsc`; `node engines/motion/pipeline/check.mjs` reproduces `questionsHash 5ab19d44…`; `node tools/package-regression.mjs` byte-identical; both finalized batches validate.
- One scratch v2 batch (library/_dev or a Pi test path, never a real one) imported, approved and scheduled on a Pi test instance end to end; a v1 batch alongside it.
- On the Pi: UI health green, publisher and autopilot unaffected through at least one autopilot run, every unit within its memory cap.
- Local main = GitHub main = Pi.

## Rules

- Everything in `AGENTS.md` and the brief's standing rules applies:
  - the repo is public, so run the safety check before every push;
  - finalized batches and `library/_sources` are immutable;
  - Pi Python stays stdlib only, and the Pi never renders or encodes;
  - code reaches the Pi only through GitHub `main` + `publisher/deploy/sync-pi.sh`;
  - never edit `/opt/scalar-social/repo` or the Pi's git config;
  - never force-push or rewrite history;
  - approval, finalizing and uploading stay with the owner;
  - never pause or modify the live schedule.
- **A batch must never become invalid retroactively.** v1 stays valid forever.
- **Dependencies:** none new. Ask before any npm or pip package.
- **No paid generation** (Gemini, Veo, fal.ai) without the owner's explicit OK for that run, with a cost estimate.
- **Pushes:** pushing `main` is approved for `publisher/` and `contract/` changes; push this phase's other commits once all checks pass.
- No live posts, label tests or platform API writes without the owner's OK for each.
- Be concise. Lead with what was done and what needs the owner's decision. Flag blockers immediately.

## When Phase 4 is complete

1. Update the status line, the Phase 4 checklist and a Phase 4 log in `docs/STUDIO_PLAN.md`, and the memory files.
2. Write `docs/prompts/PHASE5_SESSION.md`, the session prompt for **Phase 5: Originals back online**. From the brief, it covers:
   - the story engine's recap and series routes → `render.json` → packager → v2 batch;
   - an `originals` playbook skill (brief → make → check: garbage, rights, visual QA → package → owner checkpoints → finalize only on approval);
   - the prompt builder's Originals path end to end;
   - the remaining story bugs that block paid runs (B3, B7, B8, B9, unpriced LLM/image/TTS spend, submit timeouts) before any paid run;
   - planning the first small Originals batch and presenting its brief to the owner, with no paid generation, finalize or upload without the owner's explicit approval each time.

   Use the same structure as this prompt: Read first, State at handoff (verified facts only), Target structure, Remaining follow-ups, Phase scope, Verification, Rules, and a closing section. Phase 5 is the last planned phase: end that prompt by asking the session to write a short "after Phase 5" note in the plan (what is left, what to watch) instead of another phase prompt.
3. Give the owner that prompt in your final message, ready to paste into a new session started in `~/Personal/code_projects/StudioZero`.
