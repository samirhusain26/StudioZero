# Marketing system rebuild plan

Started 2026-10-07. Source prompt: `docs/NEXT_SESSION_PROMPT.md` (Part B; kept in the private scalargame-marketing-plan archive). This file is the running checklist, the record of locked decisions and the list of open questions, so the work can span several sessions.

## Safety net

- Full backup (excludes node_modules, social/ui/node_modules, .venv, .audio-work; includes .git, library/, out/):
  `~/Backups/scalar-video-pre-rebuild-20261007-232417.tar.gz`, 839.5 MB, 2,478 entries,
  sha256 `d367bba758784f873aa4fbe8d64cb6d67368c24b6082c6e18f276369bd3059b0`.
- Game repo baseline before any change: `git -C scalargame status --short` = 42 lines (40 modified, 2 untracked: `docs/growth/`, `tectonic-content/tests/globe-adjacency.test.mjs`). None of them may be staged by this work.

## Checklist

- [x] Phase 0: inventory, backup, decisions, first commit (Checkpoint A, approved 2026-10-07). History rewritten and force-pushed: `95e2e9c` (root, no media) and `c52e806` (tracked publishing system). Local `.git` went from 169 MB to 14 MB. Note: the first rewrite attempt (`8dd3c4e`/`ea2a575`) missed `public/capture` and `public/whenabouts` because of an over-anchored path filter. It was redone the same night and force-pushed again.
- [x] Phase 1: new structure and names in place (Checkpoint B). Built and independently reviewed on 2026-10-08. Staged: 288 renames, 55 legacy deletions, 9 additions. Results: publisher tests 297 OK (1 skipped), contract tests 39 OK, UI typecheck/lint/71 vitest/build/`check:static` pass, studio tsc passes, both batches validate, markers byte-identical, pilot stills byte-identical, `check.mjs` hash unchanged, and a full re-render of scalar-clues-001 is byte-identical to the finalized MP4.
  - Review fixes applied: the installers refuse to run without `contract/library_contract.py`; `MANIFEST.json` is not installed on the Pi; `/out/` and `/public/` backstop ignores added; the UI `sourceHash` now covers build inputs only; the unused `Music` component (pointing at a deleted path) was removed; `test_check_media.py` replaces the coverage lost with `test_music.py`; the `render.mjs` codeHash now includes `src/fonts.ts` and `src/Root.tsx`.
  - Known: `studio/.venv` was moved, so `bin/activate` and `pip` shims still point at the old path. Use `studio/.venv/bin/python -m pip`, or recreate the venv in Phase 2. The Pi keeps stale legacy `.py` files until Phase 3.
- [x] Phase 2: move into `scalargame/marketing/` (Checkpoint C). Moved on 2026-10-08 with a plain `mv`, so the repo, its remote and its history are unchanged. `studio/.venv` was recreated with identical packages (the old copy is in the scratchpad until Checkpoint C). `GAME_DIR` resolves to the parent folder. Marketing results: publisher 297 OK, contract 39 OK, UI 71 tests plus `check:static`, studio tsc, both batches validate, markers byte-identical, stills byte-identical, `check.mjs` hash unchanged. Game repo results: `.gitignore` `/marketing/`, `.vercelignore` (verified from CLI source that the defaults, including `.env.local`, still apply and `.gitignore` is never read), ESLint `globalIgnores`, Vitest `exclude`, Vite `server.watch.ignored` and `optimizeDeps.entries`. Vitest passes 151 files / 1,066 tests (`vitest list` finds 0 marketing files), lint passes, and the build passes with **CSS byte-identical** to the pre-move build (so Tailwind does not scan `marketing/`). The dev server serves `/` and `src/main.tsx` with no errors. Growth docs: the MARKETING_VIDEO_PLAN decision is superseded and B10 was added to the VIDEO_GENERATION_PIPELINE register.
- [x] Phase 3: Pi self-update from GitHub (Checkpoint D). Built and integrated on 2026-10-08, then hardened over three independent security reviews (L15, L16, plus Linux first-run fixes). The 7-scenario Mac demo passes, including automatic crash rollback. Approved and committed 2026-10-08. Builders were dispatched on 2026-10-08 against [REBUILD_CONTRACTS.md](REBUILD_CONTRACTS.md): A1 handles the updater, units and scripts; B handles the UI.
- [x] Phase 4: UI covers the whole loop, plus built-in Guide (Checkpoint E). Integrated: 133 UI tests; 375 px checks done in the in-app browser (overflow 0, no tap target under 44 px, answer hidden until Reveal). The Playwright e2e was not run because no browsers are installed. Approved and committed 2026-10-08. A2 handles the library backend, B the UI, C the guide content.
- [x] Phase 5: batch notes instead of a contract change (L9). Integrated. A2 builds the backend and B the UI.
- [x] Phase 6: `/video-batch` skill, fact-checker agent, templates, retros, NeighborClues enclave fix (Checkpoint F). Pipeline parameterized with a per-set `CONFIG`; 2026-10 reproduces byte-identically. Rehearsal batch `library/_dev/2026-10-dryrun2` (2 episodes) went brief → validate and stopped before finalize. Approved and committed 2026-10-08. Builder C.
- [ ] Finish: independent review, both repos green, docs and decision register

## Locked decisions

| # | Decision | Date |
|---|---|---|
| L1 | Folder `scalargame/marketing/`. The owner renames the GitHub repo `scalargame-marketing-plan` → `scalargame-marketing` (GitHub redirects the old URL). | 2026-10-07 |
| L2 | Top-level layout: `studio/` (Mac), `publisher/` (Pi), `contract/` (shared), `library/`, plus docs. | 2026-10-07 |
| L3 | Legacy code (old auto-bank, replenish job, launch-set compositions): commit it once so it is in history, then delete it from the tree. No `legacy/` folder. | 2026-10-07 |
| L4 | Rewrite history to drop large media (out/*.mp4, public/capture, public/music) and slim the repo. This needs a force-push, which the owner approves separately at the time. | 2026-10-07 |
| L5 | Legacy launch-set media (out/*.mp4, public/capture, public/whenabouts, launch mixes hero*/playalong/teaser .m4a) is deleted from disk. The only copy is the backup tarball. | 2026-10-07 |
| L6 | The owner's six source tracks `public/music/1–6.mp4` (inputs to `music_beds.py`) are kept on the Mac only, in an ignored `studio/music/sources/`. The cut beds and rights metadata are tracked. | 2026-10-07 |
| L7 | The Pi gets a committed, script-built UI bundle in a dedicated folder, with a manifest and a check that it matches a fresh source build (Finalyst pattern). No npm build on the Pi. | 2026-10-07 |
| L8 | Retros live in `library/_retros/<batchId>.md`, briefs in `library/_briefs/<batchId>.md`. They are tracked and never inside a batch folder. | 2026-10-07 |
| L9 | **No contract change.** BATCH_CONTRACT stays v1. The Pi UI gets a separate "batch notes" upload (brief/retro text, size-capped, may contain answers, shown behind the spoiler toggle). Phase 5 becomes this feature instead of a contract edit. | 2026-10-07 |
| L10 | Episode feedback is quick tags plus a free note, with no ratings. Proposed tags: keep, tweak, drop, hook weak, too hard, too easy, great reveal, visual issue, fact check, music. | 2026-10-07 |
| L11 | The Guide is edited in the repo only (`publisher/ui/content/guide/*.md`), bundled into the UI build, and shown read-only with the running commit and last-updated date. | 2026-10-07 |
| L12 | The scout app is dead. The Pi (hostname and login user `scout`) is now the marketing device. Scalar keeps `127.0.0.1:8765` and Tailscale Serve `/`. The scout **app** is removed by a dry-run-first script the owner runs with sudo. The `scout` login user stays. | 2026-10-07 |
| L14 | `studio/music/rights.json` is kept as a rights record for the launch music. | 2026-10-08 |
| L15 | Hardening after the security review (M1, reproduced): the update unit stays user `scalar-social`, but git and ssh read only root-owned config. That means `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM`, hooks and fsmonitor off, `HOME` plus `ssh -F` plus the key and known_hosts under the root-owned `/etc/scalar-social-update`, and `ReadWritePaths` narrowed. Root-owned copies of root-run code are deferred, with the trust boundary documented. Bootstrap clones the current GitHub name `scalargame-marketing-plan` (GitHub redirects old names after a rename; the updater accepts both). | 2026-10-08 (approved by owner at Checkpoint D, 2026-10-08) |
| L16 | Second security re-review (same-UID `/proc/<pid>/cwd` write into the checkout; root Python loading user-site `.pth` from HOME): a dedicated system user `scalar-social-update` owns the checkout and reads the deploy key; `scalar-social` gets read-only access. Every root-run Python uses `python3 -I -B`. The typed-confirmation bypass by a compromised `scalar-social` process (limited to GitHub main's tip) is documented, with signed-commit verification as future hardening. | 2026-10-08 (approved by owner at Checkpoint D, 2026-10-08) |
| L13 | Tracked in git: each `library/*/batch.json` and the frozen source snapshots `library/_sources/**` (8.7 MB, evidence for finalized batches). `library/_dev/` and all batch media, review files and markers stay local. | 2026-10-07 |

## Open questions

- (none blocking Phase 0 or 1)

## Pi facts (read-only SSH, 2026-10-07, approved by the owner)

- Host `scout`, aarch64, **415 MB RAM**, 106 GB free. git 2.47.3, Python 3.13.5, Node v22.23.3 (`/opt/node22`).
- Running: `scalar-social-ui` (active, `127.0.0.1:8765`), `scalar-social-approve.path`, monitor, threads-refresh and instagram-refresh timers. `scalar-social.timer` (publishing) is not active, so publishing is paused.
- `scalar-social-threads-refresh.service` is **failed**. This is outside rebuild scope; it is listed for the owner.
- Tailscale Serve: `https://<pi>.<tailnet>.ts.net` `/` → `http://127.0.0.1:8765`.
- User `scalar-social` (uid 999) has its home at `/var/lib/scalar-social` (nologin). `/opt/scalar-social` is root-owned and holds `deploy/ node_modules/ package*.json scripts/social/ ui/`. The installed scripts include stray files (`instagram_adapter.before-owner-fix-*.py`, `scalar-buffer-recover.py`, `schema-probe.py`, `deploy_threads_media.py`).
- Scout app to remove (L12): units `scout-web.service`, `scout-briefing@.service`, `scout-job@.service`, timers `scout-{availability,backup,briefing-0700,briefing-0715,briefing-0730,collect,route,router-devices,router-usage}.timer` (all disabled; scout-web failed); code `/home/scout/scout` (58 MB, uv venv); `/etc/scout` (secrets.env), `/var/lib/scout`, `/var/log/scout`, `/etc/sudoers.d/scout`, `/home/scout/.cache/uv`, `/home/scout/.local/bin/uv`; `~scout/.ssh/scout_github_ed25519{,.pub}` plus the `Host github.com` block in `~scout/.ssh/config`.
- Stray secret on the Pi: `/home/scout/.scalar-social-staging/THREADS_ACCESS_TOKEN` (a plaintext token file in the staging dir). The cleanup script will offer to shred it once the owner confirms the credential is installed under `/etc/scalar-social/credentials`.

## Baseline before any move (2026-10-07)

- Python: `python3 -m unittest discover -s tests/social -p 'test_*.py'`: 339 tests OK (1 skipped).
- Node: `node --test tests/social/content.test.mjs`: 9 pass.
- UI (`social/ui`): typecheck, lint, 71 vitest and build all pass.
- `library_contract.py validate` passes for both `2026-10-pilots` and `2026-10-b01`, each with 1 warning (`generator.dirty`). Markers are copied to the scratchpad.
- Pilot stills (`LibraryEpisode`, frame 300, deterministic: a re-render gives the same hash):
  - scalar-clues-001: `593a1ff2fc92044b7663955af5ad98bbe4e91c905c6100d5d2327162792efbbe`
  - tectonic-missing-001: `ea690ad338f8fa38d79aa681c852894567264a4e2e2eb1cc062f94f87155c73c`

## Checkpoint A commit plan

1. **Rewrite the root commit** `7e7deb5` into a new root with an identical tree, minus 165 MB of media: `out/*.mp4` (15), `public/capture/**`, `public/whenabouts/**`, `public/music/*.m4a`, `public/music/*.mp4`. `public/music/TRACKS.md` stays. The working tree is not touched; the files remain on disk until Phase 1 deletes or moves them.
2. **Commit 2**: the new `.gitignore`, the 8 modified tracked files, and 323 untracked files (16.6 MB): `scripts/social` (54), `social/` docs, prompts, profile assets and UI source (89), `deploy/pi` (22), `tests/social` (37), `src/library` (28), `src/scenes/social` + `src/data/social-bank.json` (legacy, deleted in Phase 1 per L3), `public/library` fonts and beds (26), both `batch.json` files, `library/_sources/**` (60), and `docs/{UPLOAD_PLAN,NEXT_SESSION_PROMPT,REBUILD_PLAN}.md`.
3. Push = **force-push** to `origin main` (the rewrite). Ask first.
4. After the push succeeds: `git reflog expire --expire=now --all && git gc --prune=now` so the local `.git` drops the old media blobs. The backup tarball keeps the original `.git`.


## Phase 0 findings (differences from the prompt's facts)

- `prepare.py` is **not** legacy. `runner.py` (the live `--catalog` path), `ui_approval.py` (`deploy_site`), `ui_library.py` (`caption`), `simulate.py`, `media_probe.py` and the `*first_post.py` scripts all import it.
- `add_music.py` is effectively legacy (only `render-batch.mjs` calls it; `test_music.py` tests it).
- `src/scenes/social` and `src/data/social-bank.json` are wired into the modified `src/Root.tsx` (SocialSelfContained/SocialChained) and `scripts/render.sh`. `test_prepare.py`, `test_first_post.py` and `content.test.mjs` also read `social-bank.json`. Deleting them means editing those files.
- The `library/` ignore rules exist only in the uncommitted `.gitignore` change.
- `READY_FOR_UPLOAD` hashes only `batch.json` (`batchJsonSha256`). Extra files in a batch folder don't break validation, but the hard rule still forbids writing into finalized folders.
- The validator rejects unknown top-level fields ("Unknown field (contract change needed)"). Any `notes` field in v1.1 therefore needs the Pi updated **before** a batch that uses it is uploaded.
- `library/_sources/2026-10-06-3921b9e` (the frozen snapshot that `check.mjs` depends on) is ignored and local only.
- The Pi deploy scripts depend on ignored build output: `social/ui/dist` and `out/social-site/catalog.json` plus clips.
- No test file backs the "mutation-tested" claim for `check.mjs`.
- `deploy/pi/*-credential.conf` are `LoadCredential=` drop-ins that point to `/etc/scalar-social/credentials/*`. They hold no secrets and are safe to commit.
- Ignored screenshots under `out/` (`x-oauth-review.png`, `social-qa/*token*.jpg`) may show tokens. They must never be committed.
- Port and alias conflict: scout's repo also serves `127.0.0.1:8765` behind Tailscale Serve, and its `setup-github-key.sh` appends `Host github.com` to the scout user's `~/.ssh/config`. What actually runs on the Pi is unverified (needs a read-only SSH check that the owner approves).

## Phase 1 target tree and move map

```
<repo root>/                     # scalar-video today; scalargame/marketing after Phase 2
  README.md  AGENTS.md  CLAUDE.md (identical content)  .claude/launch.json
  docs/                          # MARKETING_VIDEO_PLAN, UPLOAD_PLAN, NEXT_SESSION_PROMPT, REBUILD_PLAN, prompts/
  studio/                        # Mac: making videos (its own Node project)
    package.json package-lock.json tsconfig.json remotion.config.ts  node_modules/ .venv/ .audio-work/ out/ (ignored)
    src/index.ts src/Root.tsx    # only the LibraryEpisode composition (ID kept stable)
    src/episodes/                # was src/library (episode templates, styles, kit, timing, types)
    src/kit/sfx.tsx              # plus any other src/kit file that episodes still import
    public/sfx/  public/episodes/{fonts,music}/   # was public/library
    pipeline/                    # was scripts/social/generate/*.mjs, music_beds.py, README.md
    render/                      # render.sh, check_sync.py, master_audio.py, qa_media.py, contact.py
    tools/make_sfx.py
    music/TRACKS.md  music/rights.json  music/sources/ (ignored: the owner's 1–6.mp4)
  publisher/                     # Pi: everything the Pi needs
    app/*.py                     # was scripts/social/*.py (runtime, minus contract and legacy)
    app/static/                  # committed UI build + MANIFEST.json (L7), written by ui/scripts/build-static
    ui/                          # was social/ui (source)
    deploy/                      # was deploy/pi
    tests/                       # was tests/social (minus contract and legacy tests)
    docs/                        # was social/*.md (minus BATCH_CONTRACT.md)
    profile-assets/  config.example.json  pi-package.json  pi-package-lock.json
  contract/                      # shared: library_contract.py, BATCH_CONTRACT.md, tests/
  library/                       # batches; _sources tracked; _retros/ _briefs/ _templates/ (Phase 6); _dev ignored
```

Deleted (L3/L5): `scripts/social/{replenish,install_replenishment,add_music}.py`, `render-batch.mjs`, `build-bank.mjs`, `content.mjs`; `tests/social/{test_replenish,test_music}.py`, `content.test.mjs`; `src/scenes/**`, `src/data/**`, the launch-only `src/*.tsx` and `src/kit/*`; `scripts/capture`, `scripts/data`; `public/capture`, `public/whenabouts`, the launch `.m4a` mixes, `out/*.mp4`. Pi tests that need `social-bank.json` get a trimmed fixture under `publisher/tests/fixtures/`.

Pi runtime is unchanged in Phase 1. The installers copy `publisher/app/*.py` plus `contract/library_contract.py` to `/opt/scalar-social/scripts/social/`, and `publisher/app/static/` to `/opt/scalar-social/ui`. Phase 3 then moves the Pi to a git checkout.

Generator baseline: `node scripts/social/generate/check.mjs` exits 0, rewrites `questions-2026-10.json` byte-identically (tree stays clean) and reports `questionsHash 5ab19d44…5d3d9`.

## Phase 3 design direction (from the Finalyst/scout study, 2026-10-07)

- **Network:** the UI unit has `IPAddressDeny=any`, so it cannot fetch. A path-triggered oneshot `scalar-social-update.service` handles that instead: it runs as `scalar-social`, has network, `MemoryMax≈200M`, and `ReadWritePaths` set to the checkout plus `/var/lib/scalar-social`. The UI writes `update/check-request.json` or `update/apply-request.json` (with the confirmed SHA). The unit fetches, stages and switches, and writes the atomic `update-status.json`. The UI stays offline and only reads local git state.
- **Restart without root:** the UI runs a watcher thread on the status file. When the phase is `switched` and on-disk HEAD differs from the running commit (full SHAs), it writes `restarting` and calls `os._exit(86)`. `Restart=on-failure` then brings it back on the new code. On boot, a reconcile step marks the update `complete` or `failed`. The running commit is primed as the first statement of `main()`.
- **Git sequence:** `fetch origin main` (with `pack.threads=1` and low memory limits), `rev-parse origin/main`, `merge-base --is-ancestor`, and refusal on dirty, diverged, wrong branch or wrong origin. Confirmation must be `UPDATE TO <full sha>`, re-resolved on the server. Staging uses `worktree add --detach` in a dir under `/var/lib/scalar-social/update/` (not PrivateTmp; superseded by L15: `<repo>/.git/scalar-update-stage/`, written only by the update user). Staged checks come next. The unit waits for the `runner.lock` flock with a timeout, then runs `merge --ff-only <sha>`, with `reset --hard <old>` on failure. The worktree is removed in a `finally`. `git pull` is never used (Finalyst 46cb1bf: FETCH_HEAD race).
- **Key and clone:** a partial plus sparse clone (`--filter=blob:none`; sparse to `publisher/` and `contract/`) at `/opt/scalar-social/repo`, owned by `scalar-social` so no `safe.directory` is needed. A read-only deploy key lives at `/var/lib/scalar-social/.ssh/` with the alias `github.com-scalar` and a pinned GitHub `known_hosts` (StrictHostKeyChecking=yes, not accept-new). (Superseded by L15: the key, ssh config and `known_hosts` live in the root-owned `/etc/scalar-social-update`, and the checkout belongs to the dedicated user `scalar-social-update`.)
- **Never automated:** unit changes and `pi-package*.json` changes (`/opt/scalar-social/node_modules`, wrangler). The UI shows "run: sudo …/publisher/deploy/apply-units.sh". On a 415 MB Pi, `npm ci` stays an owner step.
- **Patterns not to copy:** scout's lack of a rollback or startup check, Finalyst's in-memory-only phases, and short-vs-full SHA comparisons (scout ae1da84).
