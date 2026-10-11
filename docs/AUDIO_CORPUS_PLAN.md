# Audio corpus plan: calm music beds and SFX

Research 2026-10-09. Owner chose **free libraries only** for music (no AI music).

## Status (2026-10-09)

- **Music corpus: 134 CC0 tracks**, all in `studio/music/sources/` (ignored, Mac only; `LICENSE.txt` per source):
  - `holizna/` (46): HoliznaCC0 lo-fi packs.
  - `oga/` (88): 46 OpenGameArt items. Each item page was re-checked on download and shows the single licence CC0. Each item is matched to the game whose brief it fits.
- **Catalog:** `studio/pipeline/music_catalog.py` → `studio/music/catalog.json` measures tempo, key/mode, percussive and bass share, loudness and brightness. It scores `quizFit` against the brief below and marks **15 `pick`s per game**:
  - best fit first;
  - steady or beatless;
  - not clearly minor;
  - at least 40 s long;
  - no near-duplicate uploads.
- **Beds:** `studio/pipeline/music_beds.py --picks` cut **90 calm beds**, `<game>-<duration>-<trackId>.m4a`:
  - one bed per pick for each duration its game's formats use: Scalar 24, Continuum 20/22, Whenabouts 22, Tectonic 22/24;
  - each is one contiguous window with a downbeat exactly on the reveal;
  - −20 LUFS, true peak ≤ −1.4 dBTP;
  - stored in `studio/public/episodes/music/` with provenance in `beds.json` (`game`, `trackId`, `page`, `license`, `segments_s`).

  The six legacy Gemini beds are unchanged, and the frozen 2026-10 set still uses them.
- **SFX:** 4 Kenney CC0 packs + 58 procedural candidates (`studio/tools/make_calm_sfx.py`) in `studio/sfx/sources/` (ignored). 302 fit the calm look.
- **Audition:** `studio/pipeline/audio_review.py` → `studio/out/audio-review/index.html`. Serve it with the `.claude/launch.json` "audio-review" config, then open `http://localhost:8790/out/audio-review/`. Picks are starred; reject vetoes one.
- **Previews:** `studio/out/music-preview/<game>.mp4`, one real episode per game with its top-pick bed.
- **Rotation (live for new sets):** `CONFIG.beds: 'calm'` is the default in the `/video-batch` setup template. Each new episode gets the least recently used *track* among its game's calm beds of the right length (`studio/pipeline/lib.mjs` `bedPool`/`pickBed`), counted across every library batch, so a game cycles through all 15 tracks before repeating. A frozen episode keeps its bed. Tested on a scratch copy of the October set: 20 episodes, 20 different tracks; a re-run left all 20 unchanged. The Gemini beds are retired; they stay only for the finalized batches and the frozen regression set.
- **Next:**
  - Promote kept SFX into `public/sfx` and extend `SfxName`.
  - Optional Pixabay additions (manual download).

## Music brief (decided 2026-10-09)

Every episode has the same arc: hook question, 6–10 s think window, reveal, explanation, "comment your letter". The bed's job is **curious thinking music**. It should keep the viewer leaning in without competing with reading, and never sound sad, sleepy, epic or arcade.

- **Shared rules:**
  - Instrumental.
  - Major or neutral key.
  - 75–110 felt BPM with a steady beat.
  - Sparse plucked or mallet textures.
  - No drops, no chiptune, no heavy swells, no sad or minor-mood tracks.
  - Present from frame 1 (no long intros).
  - Sits about 6 dB under the SFX.
- **Per game:** matched to each style recipe's look.

| Game | Look | Music |
|---|---|---|
| Scalar | field notebook, index cards, rubber stamp | curious light-detective lo-fi: pizzicato, marimba, muted guitar, brushes |
| Continuum | Swiss data poster, bars counting up | clean minimal chillhop: soft synth plucks, tidy rhythm |
| Whenabouts | almanac on parchment, year odometer | warm vintage acoustic: felt piano, nylon guitar, light strings, jazz-hop |
| Tectonic | deep-navy low-poly ocean, globe | airy ambient exploration: soft pads, gentle arps, water textures |

`music_catalog.py` scores each track against this brief and suggests a game:
- **`quizFit`:** tempo fit, major/minor lean from chroma, calm rank and steadiness. Packs the artist labelled "sad" are halved.
- **`flavour`:** suggested from percussive share and brightness.

These scores only order the audition sheet. The owner's ear decides.

## Timing constraint

Reveals sit at 10, 12 or 14 s because beds are cut at 120 BPM (one bar = 2 s; `studio/src/episodes/timing.ts`). Calm music is usually 60–90 BPM. There are two ways to keep that working:

1. **Half-time at 120 BPM (or 60 BPM).** Every even second is still a beat, so the current timing and `music_beds.py` bar maths work unchanged. This is the simplest rule for generated tracks.
2. **Any tempo.** Generalise the bed cutter to trim the intro so a chosen downbeat (a gentle "lift" where a layer enters) lands exactly on the reveal. Library tracks from Pixabay or HoliznaCC0 come at arbitrary tempos, so they need this.

With calm music, the reveal doesn't need a "drop". A soft layer entry, plus the reveal SFX, is enough. Calm beds should also sit lower in the mix than now: about −20 LUFS under the SFX, instead of −14 LUFS at volume 0.8.

## Music sources (ranked)

| Source | Licence | Attribution | Content ID risk | Volume | Notes |
|---|---|---|---|---|---|
| **Stable Audio 3 Small-Music** (local) | Stability AI Community License: free under $1M annual revenue, outputs owned by the user ([licence](https://stability.ai/license), [model](https://huggingface.co/stabilityai/stable-audio-3-small-music)) | None | Low (own generations) | Unlimited | Released May 2026; trained on licensed data; generates up to ~120 s; "a few seconds" per clip on an M-series MacBook. Weights are gated on Hugging Face, so the owner must accept the licence. The text encoder brings the Gemma Terms. BPM goes in the prompt and is not guaranteed, so measure it with librosa and reject drift. |
| **Lyria 3.5** (Gemini API) | Gemini API terms: Google claims no ownership but gives no explicit commercial grant | None | Low | ~$0.08/track ([pricing](https://ai.google.dev/gemini-api/docs/pricing)) | Same provenance as today's tracks. ~2 min tracks; WAV available; SynthID watermark. BPM and key go in the prompt, and timestamps can schedule a layer entry ([docs](https://ai.google.dev/gemini-api/docs/music-generation)). |
| **HoliznaCC0** | CC0 ([OGA](https://opengameart.org/content/chill-beats-collection), [Bandcamp](https://holiznacc0.bandcamp.com)) | None | Low | Dozens of lo-fi tracks in zip packs | Human-made; quality varies, so audition each track. |
| **Pixabay Music** | Pixabay Content License ([terms](https://pixabay.com/service/terms/)) | None | **Medium**: some contributors register tracks with Content ID ([FAQ](https://pixabay.com/service/faq/)) | Hundreds of lo-fi, ambient and piano tracks | Manual download only (the terms ban systematic copying). Keep a licence record per track. Test each on an unlisted YouTube upload before rotating it in. |
| Mixkit | Mixkit Free License ([info](https://mixkit.co/llm-info/)) | Not required | Unknown | ~36 calm tracks | Supplement only. |
| Eleven Music | Commercial on Starter+ plans ([pricing](https://elevenlabs.io/pricing/api)) | None | Low | $0.15/min | Clearest written commercial grant among hosted generators. Has no BPM parameter. |
| Epidemic Sound Business / Uppbeat Business | Subscription | None | Low (whitelisting) | Huge | Paid insurance. Confirm brand terms and whether downloads stay licensed after cancelling. |

**Excluded:**
- MusicGen and AudioLDM2: non-commercial weights.
- Suno: a second label lawsuit was filed in Sep 2026.
- Udio: downloads disabled.
- YouTube Audio Library: not cleared for use off YouTube.
- BBC Sound Effects: non-commercial.
- StreamBeats: the "used as-is" clause conflicts with cutting.
- Bensound and Incompetech free tiers: a credit is required per video.

## SFX sources (ranked)

| Source | Licence | Use for |
|---|---|---|
| **Kenney** audio packs, CC0 ([support](https://kenney.nl/support)) | No attribution | UI Audio (50), Interface Sounds (100), Digital Audio (60), selected soft Impact Sounds: clicks, pops, taps, confirms, soft chimes |
| **Freesound, CC0 only** (filter `license:"Creative Commons 0"`) | No attribution | Clock ticks, paper and page flips, pencil, typewriter, marimba and wood taps. The API needs OAuth2 for original downloads; limit 500 downloads a day ([API](https://freesound.org/docs/api/overview.html)) |
| **Sonniss GDC bundles** ([page](https://www.sonniss.com/gameaudiogdc)) | Royalty-free, commercial, no attribution; no standalone redistribution | Ocean and nature ambience, paper and map foley (multi-GB, sift locally) |
| **Procedural upgrade** of `studio/tools/make_sfx.py` | Ours | Modal-synthesis marimba, wood and glass; FM bells; soft reveal shimmers; tuned notes in the bed's key |
| Stable Audio Open 1.0 (local), ElevenLabs SFX | Community License / paid plan | Custom one-offs: "soft glassy reveal", gentle success stinger |

Target is about 200 calm SFX, grouped by role:

| Role | Count |
|---|---|
| item | 30 |
| choices | 35 |
| think/tick | 25 |
| reveal | 40 |
| explain | 25 |
| cta | 15 |
| ambience | 30 |

## Proposed library shape

```
studio/music/sources/<sourceId>/            originals (ignored, Mac only) + licence snapshot per file
studio/music/catalog.json                   per track: id, title, source, url, licence, licenceSnapshot, retrieved, sha256,
                                            bpm (measured), key, mood tags, liftBar, status (candidate/approved/rejected)
studio/public/episodes/music/<bed>.m4a      cut beds, many per duration (20/22/24 s) and mood
studio/public/sfx/<role>/<id>.wav           SFX grouped by role, with studio/public/sfx/catalog.json (same provenance fields)
```

- **Rotation:** a set's `CONFIG` picks a mood pool. Each episode gets a deterministic, seeded bed from that pool, with no repeat inside a batch.
- **Contract:** no change is needed. `music.license` is free text (`contract/library_contract.py`), so it can carry `CC0`, `Pixabay Content License`, `Stability Community License`, and so on.
- **`render.mjs` `codeHash`:** covers `public/episodes` and `public/sfx`. Adding assets marks earlier jobs `staleKit`, which is expected.

## Generation workflow (local model)

1. **Prompts:** use a prompt grid of genre × instrument × key, always ending in "…, instrumental, no vocals, 120 BPM" (half-time feel). Avoid "upbeat", "catchy", "drop", "hook" and "arcade". Use "sparse, gentle, steady, minimal dynamics, loopable, no ending".
2. **Generate:** about 5 seeds per prompt, 30–60 s each, aiming for about 300 candidates.
3. **Auto-score:** librosa BPM error, onset regularity, crest factor and loudness range (to reject spiky tracks), spectral centroid (to reject harsh, bright tracks), and a vocal or speech check. Keep the top ~120.
4. **Owner review:** the owner listens on a review sheet and keeps 60–100.
5. **Cut:** `music_beds.py` (generalised) builds 20/22/24 s beds with the lift on the reveal bar, then writes `beds.json`.

## Owner decisions needed

1. Music route: local Stable Audio 3, Lyria 3.5, free libraries (HoliznaCC0 + Pixabay), or a mix.
2. Approve new tooling: the Stable Audio 3 repo + `uv` in a separate venv (~1–2 GB weights). Accepting the gated model licence is done by the owner on Hugging Face.
3. Approve downloads: Kenney packs, HoliznaCC0 packs, and optionally a Sonniss bundle. Pixabay picks are downloaded by hand.
4. Whether a one-line caption credit is acceptable (it would unlock CC-BY sources). The default is no.
