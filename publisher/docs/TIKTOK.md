# TikTok through Buffer

Decided 9 October 2026: TikTok posts through Buffer's automatic publishing from the existing **personal** account
@studiozeroflow, in Buffer Free's third channel. Buffer holds **X, YouTube and TikTok**; Instagram posts through its
direct route. No TikTok Business account or developer app is needed: Buffer holds the TikTok connection. The TikTok
Accounts API application (the private TIKTOK_APPLICATION_DRAFT record) is abandoned; it needed company
documents this hobby project does not have.

## What the code does

- **Captions**: every batch already carries a TikTok caption (`studio/pipeline/batch.mjs`: same text as Instagram
  without "link in bio", five hashtags). The scheduler leaves out any video whose TikTok caption has more than five
  hashtags, Buffer's TikTok limit.
- **Scheduling**: TikTok is gated like every other channel (connection, verified identity, passed posting test). Cap:
  25 posts a day (Buffer's TikTok limit), inside the 40-a-day Buffer total. The recommended schedule posts at 19:00
  America/New_York.
- **Publishing**: `buffer_adapter.py` checks the exact connected account before each post and confirms a post only
  when Buffer reports it sent automatically with a `tiktok.com/@studiozeroflow/video/<id>` permalink.
- **No first comments or answer replies**: TikTok has no comment route. The choices are in the caption and the video.
- **Stats**: read by the Pi from Buffer's `Post.metrics` (works on Buffer Free; Buffer refreshes them once a day):
  views, likes, comments, shares, reach and average watch time, in the per-video funnel. See MEASUREMENT.md.

## Optional on TikTok

- **Bio link**: personal accounts get a clickable website link at 1,000 followers. Until then captions name
  scalargame.com as text.
- **"Your brand" label** (More options → Ad settings → Disclose commercial content): a choice for a free hobby game,
  not a requirement. Buffer cannot set it; it can be turned on in the app after a post.
- **AI label**: the music is Gemini-generated; the publisher sends no `isAiGenerated` value (YouTube is the same).
  To turn it on, add `'tiktok': {'isAiGenerated': True}` metadata in `ui_schedule.manifest_payload`.
- Trending sounds, polls, alt text and TikTok "Promote" are not available through Buffer.

## Owner steps (Pi, over SSH as scout)

The Pi must run from the git checkout (`/opt/scalar-social/repo`, see [SELF_UPDATE.md](SELF_UPDATE.md)) at a commit
that includes this file: Pi UI → Settings → Update.

1. **Buffer**: exactly three channels connected: X, YouTube, TikTok (disconnect Instagram there; it posts directly).
2. **Apply the connection.** Reads Buffer, records the TikTok account, keeps X and YouTube tested. Every channel stays
   disabled, publishing stays paused and any approved schedule is cleared (approve a new one in step 6).

   ```sh
   sudo sh /opt/scalar-social/repo/publisher/deploy/connect-tiktok.sh
   ```

3. **One test post.** Uses a legacy clip that never went to TikTok (ep01 did). `plan` prints `planSha256`; `dispatch`
   must follow within two hours, once; repeat `reconcile` every few minutes until it shows `confirmed` and a
   permalink.

   ```sh
   run() { sudo systemd-run --quiet --wait --pipe --collect --uid=scalar-social --gid=scalar-social \
     -p LoadCredential=BUFFER_API_KEY:/etc/scalar-social/credentials/BUFFER_API_KEY \
     /usr/bin/python3 /opt/scalar-social/repo/publisher/app/first_post.py "$@"; }
   run plan --platform tiktok --episode ep02 --plan /var/lib/scalar-social/tiktok-first-post.json
   run dispatch --plan /var/lib/scalar-social/tiktok-first-post.json --approved-sha256 <planSha256>
   run reconcile --plan /var/lib/scalar-social/tiktok-first-post.json --approved-sha256 <planSha256>
   ```

4. **Check it**: open the permalink on TikTok and confirm it plays.
5. **Record the passed test.** Accepted only if the ledger holds a confirmed TikTok post with that exact permalink.

   ```sh
   sudo python3 -I -B /opt/scalar-social/repo/publisher/app/configure_paused.py --confirm-publishing tiktok --permalink <permalink> --apply
   ```

6. **Schedule**: Pi UI → Schedule → Use recommended schedule (TikTok 19:00) → review → approve → activate as usual.
