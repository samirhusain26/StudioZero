# Build StudioZero's redesigned UI locally

Paste the following into a new session opened in this repository:

---

Implement the StudioZero UI redesign locally. This is implementation work: dispatch agents, make changes, integrate, review and test. Do not stop after another audit or plan.

First read `AGENTS.md`, `docs/STUDIO_PLAN.md`, `docs/PUBLIC_SAFETY.md` and `docs/STUDIOZERO_UI_REDESIGN.md`. Inspect the interactive reference at `library/_dev/ui-prototype/index.html` and its README/source if present. It is ignored local material, not production code. The redesign handoff is the current UI direction; preserve authoritative project, contract and publishing rules. Inspect the dirty working tree and preserve all existing work.

Build within the canonical `publisher/ui` React/strict-TypeScript/Vite app and existing stdlib Python backend where needed. Use the current stack and installed dependencies. The UI can be rewritten; reuse validated engine/import/approval/scheduling behavior. Keep old deep links and operational capabilities reachable while migrating.

The experience is Studio / Review / Publish, with Settings and Help secondary. Show Scalargame, Explainers, Marathon and Originals once each. Put batches inside their project. Desktop is for creation and phone for review. Default to a short brief with an example, optional controls collapsed, and final-cut review. Explainers is topic-first, shows videos rather than batch vocabulary, and shows a research decision rather than a fake video before a cut exists.

Support the actual hybrid workflow: preserve working in-app Scalargame preview/export; provide copyable, project-aware ChatGPT/Claude Code prompts for work outside the app; then return artifacts to the same production/revision for review. Do not pretend there is a connected agent or automatic progress. Keep paid authorization and current project checkpoints explicit. Marathon is manual; Explainers is local delivery without publisher registration; Originals stays on hold.

Important: the existing publisher importer accepts finalized batches with `READY_FOR_UPLOAD`. Implement a separate minimal creation-workspace/artifact path for unfinished cuts and revisions. Do not weaken finalized import, fabricate approvals, auto-finalize, alter a publishing contract, or register Explainers to make the UI work. Preserve identities, hashes, old artifacts and approval invalidation. Cut approval, exact package approval and scheduling remain distinct.

Dispatch agents with explicit file ownership. Use a read-only source/API explorer, one bounded implementation-and-testing worker at a time by default, and independent review. If you are an Astra root, use the standing Luna/medium worker workflow through the available supported agent mechanism. Keep architecture/integration/final acceptance with the root. Every child must know it shares the workspace, must preserve others' edits, must not spawn agents, and must obey all local-only restrictions. Parallelize independent work, not edits to the same shell/types/styles/generated files.

Start with the redesigned shell and a complete local Scalargame brief → prompt → artifact return → actual fixture-video review → revision path. Then connect the existing finalized import/approval/schedule flow against isolated fixture state and cover the other projects. Continue through meaningful implementation and verification; make routine decisions autonomously. Update the handoff with completed slices and real remaining gaps.

Use a fresh task-specific fixture directory under `library/_dev`, inspect fixture setup before running it, keep publishing paused/channels disabled and use no real credentials or worker connection. Never point local development at the Pi. Run relevant targeted tests, UI typecheck/lint/test/build, affected backend regressions and desktop/mobile E2E against the isolated server. Follow the required Modern Web Guidance workflow. Inspect the actual local screens, preserve keyboard/touch access and check narrow widths. Independently review significant changes and fix findings before finishing.

Do not create or switch branches/worktrees, stage, commit, push, open PRs, deploy, touch the Pi/live schedule, run generation, add dependencies, spend money, change contracts or edit finalized/frozen evidence. Continue independent authorized work if one part requires separate approval; report the exact boundary. Do not make a fake implementation look complete by retaining demo success states.

Finish with a working local preview, changed files, verification evidence, unresolved issues and a clear continuation point. No production deployment.
