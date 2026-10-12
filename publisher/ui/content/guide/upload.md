# Upload a batch

Do this from the Mac's browser (Tailscale on), once the batch is finalized.

1. Open the Pi UI (the Pi's Tailscale Serve address, `https://<pi>.<tailnet>.ts.net`) and sign in with your passcode. The browser remembers the sign-in for up to 90 days; sign out revokes that browser session.
2. Library (or step 4 of Studio › Make a batch).
3. Drop the whole folder `StudioZero/library/<batchId>/` anywhere on the Library page, or choose it. The page lists what it expects.
4. Press Upload batch.

What happens: the browser checks `READY_FOR_UPLOAD` against `batch.json`, sends `batch.json`, then each listed video and cover in its own request. Each file is hashed while it streams and matched to `batch.json`. The `review/` folder is never sent. Files already on the Pi are skipped. Every video is measured again on the Pi; a platform it does not suit is switched off for that video, with the reason.

Adding to what is already here never overwrites anything:

| Situation | What the Pi does |
|---|---|
| New batch ID | Adds the batch |
| Same episode, same files | Nothing ("already imported") |
| Same episode, higher revision, new file | Adds a new revision that needs approval; the old one is untouched |
| Same episode, same or lower revision, different file | Rejects it: the Mac must bump the revision |
| Question already posted on an account | Imports it, but schedules skip it on that account (with the reason shown) |

Nothing is approved by uploading. Next: [Review episodes](#review-episodes).

## Batch notes

Each batch can carry two notes: its brief (`library/_briefs/<batchId>.md`) and its retro (`library/_retros/<batchId>.md`). Add them in step 5 of Studio › Make a batch after uploading. Each note is plain text up to 64 KB. Notes may name answers, so they stay behind the spoiler toggle, and they are never published. Make a batch ([Next batch](#next-batch)) shows the latest brief and retro so the next batch can build on them.

## Failed upload

- **A file stopped halfway** (network, sleep, reload): it shows as missing. Select the folder again or press Retry; files already here are skipped by hash.
- **A file is rejected because its hash or size does not match**: the file on the Mac is not the one `batch.json` describes. Do not edit a finalized folder. Ask Claude on the Mac to check the batch (`python3 contract/library_contract.py validate library/<batchId>`).
- **Validator error at import** (for example a review-by date in the past, or a caption rule): the Pi uses the same validator as the Mac. Read the message, then ask Claude for a corrected revision or a new batch. Never hand-edit `batch.json`.
- **Rejected because the revision was not bumped**: the same episode came with different files. Corrections always need a higher revision.
- A Pi reboot during an upload is safe: partial files are deleted at start; upload again.
