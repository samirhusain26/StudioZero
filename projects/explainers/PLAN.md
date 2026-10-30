# Explainers plan

Started 2026-10-13. Status: **Phase 1 done 2026-10-14.** Pilot batch `2026-10-e00`: scout → slate → C1 (Roomba + Taction haptics) → research → story → two review rounds → **C2 locked both scripts** (owner, 2026-10-14). Next: Phase 2 (voice), which needs §6 item 1 and the owner's OK for the whisper model download.

Documents: `SYSTEM.md` (how it works: team, flow, formats, rules, files) · `RESEARCH.md` (the evidence, with sources) · `tracks/patents.md` (backlog).

## 1. Decisions (owner, 2026-10-13)

- **Name:** Explainers (project id `explainers`).
- **What:** short videos that each explain one real, niche thing, researched, scripted, narrated and built as motion graphics end to end.
- **First track: Patents, any kind.** Software, mechanical, kitchen, medical, consumer tech: the world is the oyster. An exploded view is one tool, not a requirement. Other tracks come later.
- **A full team of roles**, each its own agent where independence matters: trend scout, patent researcher, story writer, fact-checker, standards editor, cold reader, art director, render critic, with the main session as showrunner (`SYSTEM.md` §2).
- **A trend scout** reads what is in the news and suggests patent topics tied to it (`SYSTEM.md` §9).
- **First episode:** Roomba cliff sensing (US 6,883,201). MagSafe: no.
- **Making in the UI:** the Pi UI sets up the batch (Studio › Make a batch) and copies the prompt; Claude Code on the Mac makes the videos. No video generation on the Pi.
- **Channels:** the same @studiozeroflow accounts as Scalargame, all 7 platforms, posted by the Pi publisher on the explainers' **own schedule lane** (§4). Scalargame's times stay as they are.
- **Cadence:** **one video a day.** More later if it works.
- **Format:** vertical 9:16, 45–75 s. No long YouTube cut.
- **Voice:** AI voice at $0: Gemini Flash TTS on the free tier (listed free of charge, checked 2026-10-13); Kokoro-82M on the Mac as the fallback.
- **Images:** the real product may be shown, from images we have the rights to; never company press renders or marketing images (`SYSTEM.md` §6).
- **Music:** a light, quiet bed under the voice, from licensed CC0 tracks.
- **No link**; captions end with a question (`SYSTEM.md` §10).
- **New dependencies:** approved as needed (Remotion packages, whisper.cpp).
- **Renderer:** Remotion, the motion engine StudioZero already ships.
- **Budget:** $0.

## 2. Decisions on the design (owner, 2026-10-14)

- **Weekly batches of 7** (batch ids `YYYY-MM-eNN`), about 3 trend-linked and 4 evergreen, so trend topics are still fresh when they post.
- **Daily cadence from the start**, with the variety rules: 6 formats, never the same two days running (YouTube's inauthentic-content rule targets template-looking channels, and these post on the same accounts as Scalargame).
- **Claude proposes the look** (3 still directions in Phase 3; the owner picks).
- **Four owner checkpoints**, about 35 minutes a week: pick the 7 topics (C1), lock the 7 scripts (C2), pilot only when something is new (C3), approve the batch (C4).

## 3. What gets built

`SYSTEM.md` §12 has the file tree. In short: the project folder (manifest, brand, formats, backlog, scout tool, packager), the explainer kit in the motion engine (composition, scene catalog, beat schema, voice/align/props/layout-check tools), the `/explainer` skill and eight agents, the contract module, the Pi UI pieces (Make a batch, Overview card) and the schedule lanes in the publisher.

## 4. Schedule lanes (publisher change)

Today the schedule has one set of times per platform (`maxPerDay` 1); a project mix places projects into those same slots, so two projects cannot each keep their own time of day.

Design: schedule inputs get **lanes**. Each lane is a project with its own platforms, weekdays, times and `maxPerDay`. Scalargame's lane = today's recommended form; the explainers lane = one time per platform, at least 2 h from Scalargame's (Threads 09:00, X 09:30, Bluesky 10:30, Facebook 12:15, YouTube 16:00, Instagram 18:00, TikTok 19:00). The autopilot refills **each lane on its own** (its own 7-day runway rule); a lane that runs out does not block the other. Home and Studio › Overview show runway per lane. Approval stays as it is: the owner approves episodes, the autopilot schedules them. Existing approved manifests stay valid.

## 5. Phases

Pipeline before renderer: the research's strongest finding is that planning is the biggest quality lever.

| Phase | Builds | Done when |
|---|---|---|
| 1. Pre-production ✅ done 2026-10-14 (pilot scripts locked) | Six agents (trend scout, patent researcher, story writer, fact-checker, standards, cold reader), `/explainer` skill (stages 0–4), `tools/scout_feeds.py`, `tools/check_episode.py` (ledger + script lint) with tests, `formats/`, `brand/voice.md` | A slate from today's trends + backlog; Roomba and one trend-linked pick researched, written, checked and locked; the owner reads every file |
| 2. Voice | Free-tier key; lint, TTS, whisper.cpp check, alignment | Both locked scripts have a voice and a `words.json` that matches the script |
| 3. Look and catalog | `brand/` (3 still directions from Claude; the owner picks), the first scene cards, beat schema, `explainer-art-director` agent | The owner picks a direction; the first cards render preview stills |
| 4. Pilot | Composition, props builder, layout check, render, `explainer-critic` agent and loop | 2 finished episodes, every critic axis ≥ 8, media QA passes (C3) |
| 5. Package and contract | `project.json`, packager, contract module (owner approval), `studio.json`, catalog export | The pilot batch validates as contract v2 |
| 6. Pi | Lanes in the publisher, the UI's Make a batch and Overview card; deploy | The explainers lane schedules on the Pi; Scalargame posting unchanged |
| 7. First week | — | 7 episodes finalized, uploaded and posting daily |

## 5a. What the pilot taught (2026-10-14)

- The independent reviewers earned their keep: every round found real errors the writer and showrunner missed (a companion patent's mechanism stated as the product's; a dropped "typically"; a banner number from a different example; a claim summary that fit only one of three claims; framing that implied a legal opinion).
- Two review rounds were enough; final one-line fixes after round 2 are recorded as resolutions and shown at C2.
- Lessons now in the system: muted-viewer banner rules (writer agent, `formats.md`); the checker flags ShareAlike/NC images and only real superlatives; CC BY-SA images are out by default; formats may mark beats optional (owner).
- Live-litigation episodes need a dated status line in the caption and a docket re-check before C4 and before posting.

## 6. Open items (owner)

1. **Free-tier Gemini key** (needed for Phase 2): create a key in Google AI Studio on a project **without billing** (the free tier only applies there; a billing-enabled key is charged). It goes in `engines/motion/.env` as `GEMINI_FREE_API_KEY`.
2. **Series name** on screen (e.g. a short recurring title for the patent episodes), or none.
3. **Contract change** for the new project module (approval at Phase 5).
