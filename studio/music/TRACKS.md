# Music tracks

> **Retired 2026-10-09:** the owner found these Gemini beds annoying. New batches use rotating calm CC0 beds (`beds: 'calm'`; `music/catalog.json`, `docs/AUDIO_CORPUS_PLAN.md`). The beds below stay only for the finalized 2026-10 batches and the frozen regression set.

> Rebuild Phase 1 (8 October 2026): the six sources now live in `studio/music/sources/` (Mac only, ignored). The launch-set beds below (`hero*`, `playalong`, `teaser` .m4a), `src/theme.ts` and the legacy `add_music.py` were deleted; the backup tarball holds them. Current library beds: `studio/public/episodes/music/beds.json` (`studio/pipeline/music_beds.py`).

Measured 2026-09-28 (librosa beat track + linear fit, 44.1 kHz). Every source is **120.00 BPM** (fits 119.98–120.01, no drift), so no time-stretch; `BPM = 120` in `src/theme.ts` stays.
Downbeat = waveform attack start (the beat tracker marks onset peaks 20–35 ms late; corrected by eye).
Cuts: `.audio-work/build_music.py` (splices 5 ms before a downbeat, 10 ms equal-power crossfade, −14 LUFS integrated, lookahead limiter, true peak ≤ −1 dBTP, AAC 192k).

## Sources

| File | Embedded title / genre | Presumed role | Measured structure (source time) | Verdict |
|---|---|---|---|---|
| 1.mp4 | "Big Prize Reveal" / Arcade Pop | Hero A (pluck/handclap) | Riff from 0.32; bass swell 8.32; **drop 16.32** (8 bars in); breakdown 32.3–40.3; full to 80.3; final hit + tail to 83.9 | Matches. Drop is 3 bars too early for bar 12, needs a repeated riff section → alternate |
| 2.mp4 | "Midday Market Rush" / Funk | Hero B (funk/brass) | Swell 0–1.1; hits 1.1–3.1; stab break 3.1–7.1; full groove 7.1 to end, gently rising, no drop | Matches. No build/drop → not hero material |
| 3.mp4 | "The Pocket Heist" / Electro-Pop | Hero C (electro-pop) | 3-beat pickup 0–1.55; intro 1.55–7.55; groove 7.55–23.55 (stop-fill at 15.3); **breakdown + riser 23.55–31.55; drop 31.55**; groove to 63.55; 2-bar outro + final hit 63.55–69.6; silence 69.6–89.2; second full take 89.2–131.6 | Matches. **Best hero** |
| 4.mp4 | "Guess It, Place It" / Bubblegum Pop, sung | Hero D (vocal) | Intro 0–7.8; full 7.8–33.8 with no drop (1-bar dip 21.8); tag 33.8–36. Lyric stream: "Which country? Which year? / Guess it, place it, drag it, drop it / Play today! / Scalar game, go play!" (cues 0, 4, 22, 26, 30 s) | Matches. Energy is flat after 0:08, so no drop for Tectonic |
| 5.mp4 | "Golden Question" / Game Show | Play-along | Clock ticks 0.09–2.09; stabs 2.09–8.09; riser 8–10; **drop 10.09**; groove; stop at 90.6, ticking 92–98, re-drop 102.1; ends 147.6 | Matches, and the intro already fits the play-along template |
| 6.mp4 | "Skipping Downstairs" / Indie Electronic | Teaser / loop bed | Pluck intro 0.59–6.59; build 6.59–8.59 with pickup swell 7.85; **kick in 8.59**; steady groove to 60.6 | Matches |

No file looks mislabeled: the embedded titles/genres and the measured structures fit the six prompts in order.

## Cut beds (studio/public/episodes/music/)

| File | Source | Segments (source s) | Length | Key hits in output | LUFS / TP |
|---|---|---|---|---|---|
| `hero_t3.m4a` (**hero, locked 2026-09-28 → copied to `hero.m4a`**) | 3.mp4 | 1.546–15.546 · 23.546–39.546 · 59.546–67.546 | 38.000 s (19 bars) | groove 0:06 (bar 4), breakdown 0:14 (bar 8), **drop 0:22.00 (bar 12)**, last groove 0:30, outro 0:34 | −14.0 / −1.0 |
| `hero_t1.m4a` (alternate) | 1.mp4 | 0.324–8.324 · 2.324–24.324 · 74.324–82.324 | 38.000 s | riff repeats at 0:08, **drop 0:22.00**, final hit 0:36 | −14.0 / −1.0 |
| `playalong.m4a` | 5.mp4 | 0.088–15.088 | 15.000 s (7.5 bars) | ticks 0–2, stabs from 2, riser 8–10, **drop 10.00** | −14.9 / −1.6 |
| `teaser.m4a` | 6.mp4 | 6.593–20.593 | 14.000 s (7 bars) | build + swell 1.25, **groove 2.00** | −14.0 / −1.4 |

Tectonic ASMR: no music (organic SFX only, per plan).

## Owner music authorization

| File | Tool | Plan (must grant commercial use) | Attribution needed? |
|---|---|---|---|
| 1–6.mp4 | Gemini (owner statement, 2026-10-05) | Owner explicitly authorized reuse (2026-09-28; reaffirmed 2026-10-05); specific generation plan not recorded | No (owner statement) |

The owner reports that all music is AI-generated with Gemini and requires no attribution. This records owner authorization, not an independent licence verification. The new SocialEpisode public test was silent by design. `out/social-qa/ep01-with-music.mp4` is a local 30-second music-backed preview with sync/spec PASS; deployed clips and catalog hashes are unchanged.

Complete automated 30-second editions now use teaser.m4a through the legacy `add_music.py` (deleted), with 0.3-second fade-in and 1.5-second fade-out. Automated mux acceptance measured 0 ms audio offset on 6 October. Chain fragments and the original deployed catalogue remain silent; Pi runtime update is staged.
