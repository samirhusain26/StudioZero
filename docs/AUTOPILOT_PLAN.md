# Autopilot: publishing with no owner steps

Owner decision (2026-10-09): fully automatic. No typed `APPROVE <hash>`, no tap, no activation command after the
first one. Pause in the UI still stops everything. Ship through push + `publisher/deploy/sync-pi.sh`.

Already shipped (`ff05ea0`, `5c9303f`, `ec870ac`): the Pi (~400 MB RAM, zram swap) OOM-killed wrangler's
upload of 23 new videos and wrangler still exited 0. `prepare.deploy_site` now requires the deployment URL in
wrangler output, logs a redacted tail when it is missing, and uploads only files the public site does not serve
yet, six per wrangler run (`STAGE_FILES`), then the whole site. `ui_approval.patient` retries each public URL
check and logs the failing URL. First activation done 2026-10-09 (manifest `74e67654`, 147 posts + 20
comments, Oct 10–30, all 7 platforms; `approval.zeroSpendVerified` is now true).

## Built (2026-10-09)

All five items below shipped; tests in `publisher/tests/test_activation.py` (AutoTests) and `publisher/tests/test_autopilot.py`. Resume after a UI pause: `sudo rm /var/lib/scalar-social/PAUSED` (owner).


1. **`activate.py --auto`** (root). Refactor the config change in `activate()` into
   `activated_config(ctx, now, zero_spend_note)`. `auto_activate()`:
   - waits (exit 0, nothing changed) until `approval.zeroSpendVerified` is true (set by the one
     `--apply --confirm-zero-spend`, done once by the owner on 2026-10-09);
   - waits while `approval.activatedAt` is set and `STATE/PAUSED` exists (owner paused in the UI);
   - runs `checklist()`, ignoring only the "timer disabled" row; any other FAIL → print and wait;
   - saves the new config when enabled channels / paused / scopeHash / flags differ (ignore `activatedAt`
     and `evidence` in the comparison), then `systemctl enable --now scalar-social.timer` if not enabled+active.
   - `--auto` always exits 0 (the next run retries). Tests in `test_activation.py`.
2. **`publisher/app/autopilot.py`**:
   - `verify-channels` (root): for a Buffer channel with identity verified, disabled and not
     `publishingVerified`, find a confirmed ledger post on its current account and call
     `configure_paused.confirm_publishing` with that permalink, then `save`.
   - `refill` (scalar-social): skip if `approval/request.json` exists. Runway = last post date (config
     `timezone`) in the approved manifest; if fewer than 7 days remain (or no manifest), build the recommended
     inputs (mirror `publisher/ui/src/lib/scheduleForm.ts` `recommendedScheduleForm`: every platform, all
     weekdays, `RECOMMENDED_TIMES`, maxPerDay 1, minGapHours 2, stagger 0, `game-round-robin`, firstComment
     and answerReply true, start tomorrow, end tomorrow+20), then the same steps as `ui_server.post_draft`
     (validate_inputs, current_manifest, ledger_history, schedulable_videos, generate, draft_sha256, insert
     draft). Skip with a message if `blocking` or `summary.filled == 0` (library used up: render a new batch).
     Otherwise `ui_approval.request_approval(state, sha, f'APPROVE {sha[:8]}', draft_exists=True)` and mark
     the draft `requested`. The approve path unit does the rest.
3. **Units**: `scalar-social-autopilot.service` (User=scalar-social, sandbox like approve.service,
   `ExecStartPre=+… autopilot.py verify-channels`, `ExecStart=… autopilot.py refill`,
   `ExecStartPost=+… activate.py --auto`) and `scalar-social-autopilot.timer` (05:15 and 17:15,
   Persistent=true). Add `ExecStartPost=+/usr/bin/python3 -I -B …/activate.py --auto` after `approval_bind.py`
   in `scalar-social-approve.service`. In `apply-units.sh`, add the autopilot timer to the always-enabled list
   next to the metrics units.
4. **UI**: `ApprovalPanel` drops the typed field; the button sends `draft.confirmationPhrase` (no API change).
   `approvalGate` loses the typed check. Copy: "Approving deploys and checks the media, then publishing starts
   automatically." Rebuild `publisher/app/static` (`npm run build:static`). Guide pages that mention typing
   APPROVE or running activate: update.
5. **Docs**: AGENTS.md/CLAUDE.md hard rule on public posting → "Autopilot schedules and publishes approved
   library videos; owner pauses in the UI." OWNER_GUIDE / guide: describe autopilot and how to pause.
