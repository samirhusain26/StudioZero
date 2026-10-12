# Session prompt: StudioZero, Phase 5 (Originals back online)

You are continuing a multi-session restructuring of **StudioZero**, the public studio repo behind the @studiozeroflow social accounts. Phases 0–4 are done. This session runs **Phase 5: Originals back online**, the last planned phase:
- the story engine's recap and series routes produce `render.json` that the packager turns into a contract v2 batch;
- an `originals` playbook skill: brief → make → check (garbage, rights, visual QA) → package → owner checkpoints → finalize only on approval;
- the prompt builder's Originals path end to end;
- the story bugs that block paid runs, fixed before any paid run;
- the first small Originals batch planned and its brief presented to the owner.

Don't re-derive or re-argue earlier decisions. Contract v2 (plan §5, `contract/BATCH_CONTRACT.md` "schemaVersion 2") is live on the Pi; device compute (decision 8) stands: the Pi never renders or encodes, and the story engine runs on the owner's laptop (the story worker) or the Mac CLI.

## Read first

1. `AGENTS.md` (the same as `CLAUDE.md`): tree, commands, hard rules, public-safety rules.
2. `docs/STUDIO_PLAN.md`:
   - the status line and §1 locked decisions;
   - §5 contract v2, §14 (story engine bugs and what Phase 2 fixed), §15 Phase 3 log (story worker, Story jobs), **§16 Phase 4 log**;
   - `docs/plan/STORY_ENGINE_REVIEW.md` (bugs B1–B10, features, cost data).
3. `docs/prompts/STUDIOZERO_CONSOLIDATION.md`: "Phase 5" and "Standing rules for every phase".
4. The contract: `contract/BATCH_CONTRACT.md` (v2 section), `contract/library_contract.py` (`validate_document_v2`, `required_attributions`, `episode_view`), `contract/projects/originals.py`, `contract/tests/test_contract_v2.py` and the fixtures `originals_v2()` in `contract/tests/contract_fixtures.py`.
5. Packaging: `tools/RENDER_JSON.md`, `tools/render-json-core.mjs`, `tools/package-core.mjs`, `tools/package.mjs`, **`projects/originals/package-core.mjs` + `package.mjs`** (built in Phase 4, not yet used on a real render), `tools/tests/package-v2.test.mjs`, `projects/originals/project.json`.
6. The story engine: `engines/story/docs/HEADLESS.md`, `src/render_json.py` (recap and series writers), `src/headless.py`, `src/cli.py`, `src/agent.py` (the worker behind Studio › Story jobs), `src/budget_guard.py`, `src/video_client.py`, `registry.json`, `tests/`.
7. Skills and builder: `.claude/skills/video-batch/SKILL.md` (the Scalargame playbook to mirror), `.claude/agents/fact-checker.md`, `publisher/ui/src/lib/promptBuilder.ts` (its Originals branch says "the skill itself arrives in Phase 5"), `publisher/ui/src/views/MakeBatchView.tsx`, `publisher/ui/src/views/studio/PlanMakeContent.tsx`, `publisher/ui/content/guide/{studio,make-a-batch,next-batch}.md`.
8. The publisher side that Originals now reaches: `publisher/app/ui_schedule.py` (`_attribution_reason`, `ai_label`, `project_mix`), `publisher/docs/PLATFORM_MATRIX.md` "AI labels".
9. Memory: `~/.claude/projects/-Users-samirhusain-Personal-code-projects-StudioZero/memory/MEMORY.md` and `studiozero_consolidation.md`.
10. `git log --oneline -20` and `git status`.

## State at handoff (2026-10-12, verified)

- **In sync:** StudioZero `main` = GitHub = Pi, at the commit that added this prompt or later. `main` has branch protection (no force-push or deletion).
- **Contract:** v1 and v2 live on the Mac and the Pi. Scalargame's `project.json` is contract v2 (owner decision 2026-10-12); the finalized 2026-10 batches stay v1 and validate on every test run; `node tools/package-regression.mjs` re-packages both byte-identical (pinned to v1). v2 has `render.renderer` (`render.sh`, `web` or null).
- **Pi:** imports v1 and v2 in one library (`episodes.question_id` = contentId); the schedule generator verifies that each v2 episode's required attributions post; AI labels are mapped per platform (Instagram, TikTok, X applied from `aiGenerated`; YouTube from `realisticSynthetic`; Facebook Reels, Threads, Bluesky have no API field and record `not-supported`). **No AI label has been exercised in a live post yet.** Mix policy exists but is off: every project's `mix.target` is null, so drafts use the game round-robin exactly as before.
- **Originals packaging (Phase 4, untested on a real render):** `projects/originals/package-core.mjs` builds v2 episodes from story render.json + `review/originals.json` (`{reviewer, experimentId?, episodes: {<episodeId>: {checks: {rights, garbage, visualQa}, hook?, reviewBy?, revision?}}}`), contentId `originals:<format>:<slug>` (recap: title + year; series: project + episode). A platform whose caption limit cannot hold the caption plus its attribution gets no caption and a warning: with today's story attribution texts (TMDB ≈ 130 characters, Wikipedia ≈ 130) a recap would not post on X or Bluesky.
- **Gaps between the story engine and contract v2** (each makes the packager or validator refuse a real render today):
  - episode ids: the story engine writes `originals-recap-<slug>` and `originals-series-<project>-ep<n>`; contract v2 wants `originals-<format-slug>-<nnn>` (3+ trailing digits, unique forever), and the packager wants the job folder named after the id (`library/<batchId>/review/jobs/<episodeId>/render.json`, media at `videos/<episodeId>.mp4`, `covers/<episodeId>.jpg`);
  - licences: recap renders credit the music (`engines/story/assets/music`, provenance unknown), the stock fallback clips (`assets/basevideos`) and the caption font (Arial Black, system) as `unknown`; v2 refuses `unknown`;
  - costs: LLM, image and TTS spend is not priced (`costUsd` 0 with `costEstimated: true` for recaps).
- **Story engine bugs still open and blocking paid runs** (plan §14): B3 (no series TTS; mixed audio/no-audio clips concat to a silent final; mixed resolutions stream-copied), the rest of B7 and B8 (Seedance endpoints unverified, fallback order not by price), B9 (dead Vertex path), LLM/image/TTS spend not in the ledger, a submit that times out after sending is neither retried nor counted. Fixed: B1, B2, B4, B5, B6 (B10 partly; see §14 and §15).
- **Toolchain:** system ffmpeg on the Mac is broken; the Remotion-bundled ffmpeg lacks the recap renderer's filters (`setsar`, `fps`, `loop`, `asplit`, `aloop`, `sidechaincompress`, `ass`), so a real recap render needs a full ffmpeg (owner decision still open). The $0 smoke test runs both routes with a stand-in renderer.
- **Owner decisions still open:** whether Originals links (optional in contract v2; none exist yet) need a host allowlist (Phase 4 security review; the review screen shows every link target); target mix shares per project; the Originals monthly budget (`monthlyUsd: 0`, per-run approval); a full ffmpeg on the Mac; the laptop worker set-up (Tailscale Serve + `scripts/agent-token.py --send-to-pi`); Safari 26 and phone export checks.
- **Publisher at handoff:** a Bluesky post of 2026-10-12 14:30Z was waiting for remote confirmation (`remote_confirmation_pending`, re-checked hourly); if it is still uncertain, it is the owner's to resolve (never re-post).

## Target structure

```
Story engine (laptop worker / Mac CLI)            Packager (tools/, projects/originals/)            Pi (unchanged in Phase 5 unless a fix needs it)
- recap and series routes                         - stages renders into library/<batchId>/          - imports the v2 batch, verifies attributions,
- render.json per episode with contract-ready       review/jobs/<episodeId>/ (+ videos/, covers/)     applies AI labels, schedules (mix once the
  ids, known licences, priced cost                 - originals core → v2 batch.json → validator        owner sets targets)
                                                  - review/originals.json from the playbook's
.claude/skills/originals/ (playbook)                checkpoints
- brief → make → check → package → checkpoints
- finalize only on the owner's approval
```

## Remaining follow-ups

- Ask the owner the open decisions when they come up: the Originals monthly budget before any paid run, target mix shares before Originals is scheduled alongside Scalargame, a full ffmpeg before a real recap render. Never invent values.
- Attribution wording for X and Bluesky (shorter attribution text where the licence allows it, or accept that recaps skip those platforms): propose, the owner decides; any change to the contract's attribution rule is a contract change.
- The first live AI-labelled post (Instagram `is_ai_generated`, Buffer `isAiGenerated`) is a live test: owner OK first, then watch the job and the public post.

## Phase scope (ship in small, green steps)

Build in this order. Get each step green, commit and ship it before starting the next. Nothing here changes the Pi's publishing path unless a step finds a bug there; if it does, that fix ships alone, after its tests, and is watched through one autopilot run.

### 1. Story engine → contract-ready render.json ($0)
- Episode ids the contract accepts (`originals-<format-slug>-<slug>-<nnn>` or a numbered scheme the playbook assigns; unique forever) and a staging step (CLI or tool) that copies a finished render into `library/<batchId>/review/jobs/<episodeId>/` with `videos/` and `covers/`, never writing into a finalized batch.
- Known licences for every asset: licensed music (or no music) instead of `assets/music`; no stock fallback clips without a licence; an OFL caption font (the motion engine's fonts are OFL) instead of Arial Black. The $0 smoke test must produce a render.json the packager accepts (`renderErrors` with `schemaVersion` 2) and a batch the validator accepts.
- Price LLM, image and TTS calls into the spend ledger and `costUsd` (with sources for the prices); count a submit that may have been sent.

### 2. Bugs that block paid runs
- B3 (series audio: TTS or an explicit silent policy, no silent final from mixed clips, normalized resolutions), the rest of B7/B8, B9, the ledger gaps above. Tests for each, at $0 (mocked providers, sockets blocked).

### 3. The `originals` playbook skill
- `.claude/skills/originals/SKILL.md` mirroring `/video-batch`: `brief <batchId>` → make (story worker or CLI; $0 offline first) → check (garbage: script sanity against the sources; rights: every credit with a known licence and its attribution; visual QA: contact sheet, frames, subtitles; AI disclosure matches the models) → package (`node tools/package.mjs --project=originals --batch=<batchId>`; writes `review/originals.json` from the checkpoints) → owner checkpoints → finalize only on approval → retro. `status` and `retro` like the Scalargame skill. The fact-checker agent (or an originals variant) checks recap facts against the sources.

### 4. Prompt builder Originals path
- Studio › Make a batch for Originals hands off to the skill (`/originals brief <batchId>` + brief + safety lines), with the formats, routes and models from the catalog; the checklist follows the skill's checkpoints. Update the guide pages.

### 5. Plan the first small Originals batch
- One to three episodes. Present the brief to the owner: titles, format, route, models, a cost estimate per episode and in total, credits and licences, the AI disclosure and labels per platform, which platforms will post (attribution length), and the mix question. **No paid generation, finalize or upload without the owner's explicit approval each time.**

### Then
- `build:static` + `check:static`; a short security review of anything that changed on the Pi or the worker; update the guide.

## Verification before Phase 5 counts as done

- `python3 tools/public_safety_check.py`: 0 findings, before every push.
- Contract, publisher, tools and story suites (the $0 smoke test of both routes now ends in a v2 batch the validator accepts); the agent tests at $0.
- UI typecheck, lint, Vitest, e2e, `build:static` + `check:static`.
- Motion `tsc`; `node engines/motion/pipeline/check.mjs` reproduces `questionsHash 5ab19d44…`; `node tools/package-regression.mjs` byte-identical; both finalized batches validate.
- A scratch Originals v2 batch from a $0 render (`library/_dev/`, never a real batch) imported, approved and drafted on a throwaway state on the Pi, next to Scalargame batches.
- On the Pi: UI health green, publisher and autopilot unaffected, every unit within its memory cap.
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
- **No paid generation** (Gemini, Veo, fal.ai; LLM, image, TTS or video) without the owner's explicit OK for that run, with a cost estimate. Paid runs stay off in the worker unless the owner sets `STUDIO_AGENT_ALLOW_PAID=1` for that run.
- **A batch must never become invalid retroactively.** Contract changes (including the attribution rule and new project modules) need the owner's approval.
- **Dependencies:** none new. Ask before any npm or pip package, and before installing a system package (a full ffmpeg is the owner's decision).
- **Pushes:** pushing `main` is approved for `publisher/` and `contract/` changes; push this phase's other commits once all checks pass.
- No live posts, label tests or platform API writes without the owner's OK for each.
- Be concise. Lead with what was done and what needs the owner's decision. Flag blockers immediately.

## When Phase 5 is complete

1. Update the status line, the Phase 5 checklist and a Phase 5 log in `docs/STUDIO_PLAN.md`, and the memory files.
2. Phase 5 is the last planned phase: instead of another session prompt, write a short **"After Phase 5"** section in `docs/STUDIO_PLAN.md`: what is left (open owner decisions, deferred items, known debt) and what to watch (autopilot runs, AI labels on the first live posts, spend against the Originals budget, the mix once targets are set, Pi memory).
3. Give the owner a concise summary in your final message: what shipped, what needs their decision, and the first Originals brief awaiting their approval.
