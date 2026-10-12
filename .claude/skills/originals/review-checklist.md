# Originals review: script, rights, frames, disclosure

All review output goes in `library/<batchId>/review/` (never uploaded) while the batch is **not** finalized. Each section ends in one line per episode in `review/checkpoint1.md`.

## 1. Garbage (script sanity)

Recap (`review/jobs/<id>/script.json`, `render.json` → `job.plotSource`, `job.plotUrl`, `job.tmdbId`):
- The narration tells **this** film's plot: names, order of events, ending. The originals-fact-checker agent checks every claim against the plot source; read its `review/source-verification.json` and settle every `concern`/`fail` with Samir.
- No invented scenes, quotes or numbers; no "based on a true story" claim unless the source says so.
- Hook (scene 1 and the caption hook): attention-grabbing without giving away the twist or ending; no clickbait the video does not deliver.
- Nothing unsafe or defamatory about real people; no slurs; sensitive themes (violence, abuse) told without graphic detail.
- Narration language and pronunciation of names make sense (Samir listens; you read the script).

Series (`output/projects/<P>/story.json`, `episodes/episode_<n>/director_shots.json`):
- The episode follows its outline and makes sense on its own in under a minute.
- No real people, real brands or logos, no copyrighted characters in prompts; nothing unsafe.

## 2. Rights

For each credit in `review/jobs/<id>/render.json`:
- **Footage (Pexels):** creator and page present; open the page if anything looks off (the Pexels licence needs no attribution, but the caption credits are kind).
- **Poster and data (TMDB):** the attribution carries "This product uses the TMDB API but is not endorsed or certified by TMDB".
- **Plot text (Wikipedia, CC BY-SA 4.0):** the article URL and the attribution text.
- **Music (CC0):** artist and page; the track's catalog entry in `engines/motion/music/catalog.json` says CC0-1.0.
- **Font (OFL-1.1):** Fraunces Black (`engines/story/fonts/`).
- **Generated** (script, voice, images, clips): the model in `creator` matches `models`.
- Frames show no channel logo, watermark, burned-in subtitles from the source, or a recognisable trademark that would need clearance.

## 3. Visual QA (every episode)

```bash
engines/motion/.venv/bin/python .claude/skills/originals/contact_sheet.py library/<batchId>/videos/<id>.mp4 library/<batchId>/review/frames/<id> 12
```
Read `sheet.png` and each full-size frame:
- 1080x1920, no black, frozen or garbled frames; no letterbox bars from a landscape stock clip.
- Captions (recaps): readable, one or few words at a time, inside x 90–990 and y 270–1540, in sync with the narration (spot-check three frames against `script.json`).
- Stock clips fit the narration (no obviously wrong subject); the poster end card shows the right film.
- Series: characters consistent between shots, no warped faces or hands, clean joins, nothing cut mid-word.
- Technical facts from `render.json`: duration (Facebook Reels takes ≤ 90 s, Bluesky ≤ 60 s, X ≤ 140 s: the Pi skips a platform the duration does not fit), `job.conformed` (what the engine re-encoded), `job.audio` (series).

## 4. Disclosure

- `models` lists every generative model that made something in the video; `disclosure.aiKinds` covers them (script, voice, image, video, music).
- `realisticSynthetic`: true when people, places or events look real (YouTube's label); a stylised animation is false.
- Labels the Pi will apply: Instagram, TikTok and X from `aiGenerated`; YouTube from `realisticSynthetic`; Facebook Reels, Threads and Bluesky have no field (recorded as not supported).

## 5. checkpoint1.md

| Episode | Title / episode | Script (fact-check) | Rights | Frames | Disclosure | Cost (estimate → actual) | Hook |
|---|---|---|---|---|---|---|---|
