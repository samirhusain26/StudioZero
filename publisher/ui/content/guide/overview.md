# How it works

Scalargame's social videos are short quiz clips. They are made in batches on the Mac, checked by you, uploaded to this Pi, approved here, and posted by the Pi on a schedule you approve. Only videos you approved are ever posted. After the one-time activation the [autopilot](#autopilot) schedules and publishes them by itself; Settings › Pause publishing stops everything.

The loop, start to finish. The Pi UI uses the same six steps everywhere (Home shows where you are): **Make → Upload → Review → Schedule → Post → Learn**, then the next batch.

1. **Make a batch on the Mac.** Open Claude Code in `scalargame/marketing` and run `/video-batch brief <batchId>` (or paste the prompt from Library › [Make a batch](#next-batch)). Claude writes and checks the questions, renders the videos and stops at each [checkpoint](#checkpoints) for your OK. See [Make a batch](#make-a-batch).
2. **Finalize.** After your approval Claude runs `finalize`, which writes `READY_FOR_UPLOAD`. The batch folder is now frozen. See [Finalize](#finalize).
3. **Upload.** Here: Library → drop (or choose) the folder `scalargame/marketing/library/<batchId>/` → Upload batch. Add the brief and retro as [Batch notes](#batch-notes). See [Upload a batch](#upload-a-batch).
4. **Review and approve content.** Watch each episode, leave [feedback](#feedback), approve the ones that are ready. See [Review episodes](#review-episodes).
5. **Schedule.** The [autopilot](#autopilot) adds a 21-day draft and approves it whenever fewer than 7 days are left. To change the plan, generate a draft yourself, check it and approve it. See [Schedule](#schedule).
6. **Post.** Publishing follows the approved schedule by itself (the one-time [activation](#activation) was done on 2026-10-09). Pause in Settings stops it.
7. **Learn.** Your feedback and the last retro become the next brief: Library › Make a batch → Download feedback.json into `library/_inbox/` on the Mac, then Copy prompt for Claude. See [Next batch](#next-batch).
8. **Keep the Pi up to date.** After Claude's code changes are pushed to GitHub: Settings › Update. See [Update the Pi](#update-the-pi).

Home's loop card always shows the one next step, and every screen says which step it is ("Step 3 of 6 · Review"). The ? in the header opens this guide at the section for the screen you are on.

## Where things live

On the Mac (repo `~/Personal/code_projects/scalargame/marketing`, its own git repo inside the game folder):

| Path | What |
|---|---|
| `engines/motion/` | Video maker: Remotion templates, the generation pipeline (`engines/motion/pipeline/`), rendering (`engines/motion/render/render.sh`) |
| `library/<batchId>/` | One batch: `batch.json`, `videos/`, `covers/`, `review/` (review never leaves the Mac), `READY_FOR_UPLOAD` once finalized |
| `library/_briefs/<batchId>.md` | The brief for each batch |
| `library/_retros/<batchId>.md` | The retro for each batch |
| `library/_templates/` | `BRIEF.md` and `RETRO.md` templates |
| `library/_inbox/` | Where `feedback-<batchId>.json` from this Pi goes (not in git) |
| `library/_sources/` | Frozen snapshots of game data that every batch is built from |
| `publisher/` | Everything the Pi runs, plus this UI's source (`publisher/ui`) and its built copy (`publisher/app/static`) |
| `contract/` | The batch rules and the validator both sides use |
| `OWNER_GUIDE.md` | Short Mac-side pointer to this guide |

On the Pi (SSH alias `scalar-pi`; this UI at the Pi's Tailscale Serve address, `https://<pi>.<tailnet>.ts.net`):

| Path | What |
|---|---|
| `/opt/scalar-social/repo` | The code, as a git checkout of GitHub `main`, owned by the system user `scalar-social-update` (after the one-time [git bootstrap](#first-time-setup-git-bootstrap); before it, the code was copied to `/opt/scalar-social/scripts/social` and `/opt/scalar-social/ui`) |
| `/opt/scalar-social/node_modules` | Tools for media deployment; changed only by you |
| `/var/lib/scalar-social` | All state: library index, uploaded videos and covers, posting ledger, approved manifests, the `PAUSED` marker |
| `/var/lib/scalar-social-update` | Update status, written only by the update user; `inbox/` holds the requests this UI sends it |
| `/etc/scalar-social` | `config.json` and root-only `credentials/` |
| `/etc/scalar-social-update` | Root-owned settings for updates: the read-only GitHub deploy key, its SSH settings and GitHub's host keys |
| `/var/backups/scalar-social` | Root-only copies of service files taken before installs |
| `~/.scalar-social-staging/` (the login user's home) | Folders you copy from the Mac before running a one-time install script |

On GitHub: `samirhusain26/scalargame-marketing-plan`. Renaming it to `scalargame-marketing` is optional: GitHub redirects the old name and the Pi accepts both, so nothing breaks either way.
