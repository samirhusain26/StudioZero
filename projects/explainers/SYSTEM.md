# Explainers system

How a daily patent explainer gets made, from a trend to an approved video on the Pi. Evidence: `RESEARCH.md`. Decisions, phases and open items: `PLAN.md`. Nothing here is built yet.

```
 trend feeds ─┐
 backlog ─────┴─► SCOUT ─► slate ─[C1 pick]─► RESEARCH ─► STORY ─► CHECKS ─[C2 lock]─► VOICE ─► ART DIRECTION ─► BUILD ─► CRITIQUE ─[C3 pilot]─► PACKAGE ─[C4 approve]─► Pi
                                              ledger      script    fact ·             words     beats        render   render       batch.json
                                                                    standards ·                                          critic
                                                                    cold read
```

## 1. Principles

1. **Plan before generating.** Every pixel follows a locked script and a validated beat spec. No code is written to "see what happens".
2. **Facts trace to a primary source.** Every claim in the script points at a line in the episode's ledger, and the ledger points at a patent paragraph, claim or a dated source. The story writer has **no web access**: it can only use what the researcher sourced.
3. **Independence where errors repeat.** The fact-checker, standards editor, cold reader and render critic are separate subagents with a fresh context and no stake in the script. Nobody reviews their own work. Reviewers advise; the showrunner decides; the owner approves.
4. **Choose from a catalog, don't free-write.** The art director fills a Zod-validated beat spec from a catalog of scene recipe cards. New scenes are pitched, approved and added to the catalog, so the library improves with every batch.
5. **Narration first.** The voice is generated and aligned before any visuals; scene boundaries key off word onsets, so the picture always lands on the word.
6. **The critic sees the render.** Deterministic checks first (layout, loudness, sync), then a vision critic on contact sheets and phone-size frames.
7. **Variety by design.** YouTube's "inauthentic content" rule targets videos that look template-made. Episodes rotate formats, structures and accents, and each carries information only it has (its patent figure, claim, inventor, dates).
8. **Cheap gates, capped loops.** The owner gates at the cheap, irreversible steps. Review loops stop after 2 rounds (3 for the render critic) and escalate.
9. **One file per stage.** Any stage can resume in a fresh session from its files.
10. **$0.** Free sources used within their terms, free-tier voice, local rendering.

## 2. The team

The main session is the **showrunner** (producer, story editor, content strategist): it holds the batch state, runs the stages, picks, applies or rejects notes, and talks to the owner. The other roles are subagents in `.claude/agents/explainer-*.md`, each called once per episode with a precise brief, returning content for the showrunner to save (read-only agents, like `originals-fact-checker`). This also keeps the main session's context small across a batch.

| Role | Agent | Fresh context | Tools | Gets | Returns | Rights |
|---|---|---|---|---|---|---|
| Showrunner | main session | — | all | everything | stage files, state, owner summaries | picks, decides, runs gates |
| Trend scout | `explainer-trend-scout` | yes | Read, WebSearch, WebFetch | feed digest, backlog, done list, format list | ~12 scored candidates: trend → product or practice → patent angle | proposes only |
| Patent researcher | `explainer-patent-researcher` | yes | Read, WebSearch, WebFetch | one candidate | the **ledger** (§5) | owns the facts, not the framing |
| Story writer | `explainer-story-writer` | yes | Read | ledger, format card, `brand/voice.md`, last scripts (to avoid repeats) | 2 angles and a script draft per angle | owns the words until lock |
| Fact-checker | `explainer-fact-checker` | **independent** | Read, WebSearch, WebFetch | script, ledger, patent URL (not the writer's reasoning) | per line: pass / fail / unsupported, with the source and the phrasing-ladder level | "unsupported" blocks the line |
| Standards editor | `explainer-standards` | **independent** | Read | script, asset manifest, caption draft | pass / hold per rule (§6) | can hold the episode |
| Cold reader | `explainer-cold-reader` | **independent**, sees only the script | Read | script text only | hook, open loop, payoff, loop-back scores; "what is this about after 3 s?"; ≤ 3 changes | advises |
| Art director | `explainer-art-director` | yes | Read | locked script, `words.json`, scene catalog, format card, `brand/MOTION.md` | `beats.json` (§7) with a logged decision per beat, and pitches for new scenes | owns the look within the brand |
| Motion designer | main session | — | Read, Write, Edit, Bash | approved pitch | a new catalog scene with a preview still | builds only what was approved |
| Render critic | `explainer-critic` | **independent** | Read (images) | contact sheet, phone-size frames, locked script | capped 7-axis scores and the 3 worst issues with frame numbers | advises |
| Social editor | `tools/package.mjs` + main session | — | — | episode facts | per-platform captions | — |
| Analyst | main session (retro) | — | — | Pi feedback export | what worked by format, hook type and topic → scout weights | — |

Scripted steps, no model: feed fetcher, script lint, TTS, transcription check, alignment, props builder, layout check, `render.sh`, media QA, sync check, packager, contract validator.

Model per agent (frontmatter): the scout and cold reader can run on a smaller model; researcher, writer, fact-checker and art director on the strongest. Claude usage is the real limit for a daily show, so each agent gets one call per episode and returns compact files.

## 3. The batch flow (`/explainer brief <batchId>`)

A batch is **one week: 7 episodes** (recommended over 14 so trend topics are still fresh when they post). Roughly 3 trend-linked and 4 evergreen per week.

| # | Stage | Who | Output (under `library/<batchId>/`) | Gate |
|---|---|---|---|---|
| 0 | Brief, from the UI prompt: count, formats, subjects (optional), scout on/off, notes | showrunner | `library/_briefs/<batchId>.md` (tracked), `review/explainers.json` (state) | |
| 1 | Scout: `tools/scout_feeds.py` fetches feeds once; the scout turns them into candidates; backlog adds evergreen ones | scout | `review/scout.json`, `review/slate.md` (12 candidates: hook, patent, format, evidence level, visual idea, score) | **C1: owner picks 7 and the order** |
| 2 | Research, per episode | researcher | `review/jobs/<ep>/ledger.json` | a failed status, copyright or evidence check swaps in a spare |
| 3 | Story: 2 angles + drafts; the showrunner picks and edits | writer, showrunner | `review/jobs/<ep>/script.json` | |
| 4 | Checks, in parallel; script lint; at most 2 rounds | fact-checker, standards, cold reader | `review/jobs/<ep>/checks.json`, `review/source-verification.json` | **C2: owner locks the 7 scripts** (reads each with its verdict summary) |
| 5 | Voice: TTS, transcription check, alignment, loudness | scripted | `review/jobs/<ep>/voice.wav`, `words.json` | |
| 6 | Art direction: beats from the catalog; pitches for new scenes with 2–3 stills | art director | `review/jobs/<ep>/beats.json`, `pitches.md` | new scenes: owner approves the stills |
| 7 | Build: props from beats + words; layout check on a still at every beat midpoint; render through `render.sh`; media QA; sync check | scripted, motion designer | `props.json`, MP4, `render.json`, `assets.json` | |
| 8 | Critique: fix the 3 worst issues; until every axis ≥ 8, at most 3 rounds | render critic | `review/jobs/<ep>/critic-r<n>.md`, contact sheets | **C3: pilot**, on the first batch and whenever a new format or scene ships |
| 9 | Package: captions per platform; `batch.json`; validate | packager | `batch.json` | **C4: owner reviews, finalizes, uploads on the Pi** |
| 10 | Learn: 7-day stats by format, hook type and topic | showrunner | `library/_retros/<batchId>.md`; scout weights in `tracks/patents.md` | |

Owner time per week: C1 about 5 minutes, C2 about 15, C4 about 15 (watching 7 videos with sound). C3 only when something is new. A gate is never marked passed in the state file without the owner's recorded approval.

## 4. Formats (variety)

Every episode is one of these. The showrunner never uses the same format two days running, uses at least 3 formats a week, and varies the hook type. Each format has its own beat spine and accent colour.

| Format | Spine | Example |
|---|---|---|
| **How it works** | hook → problem → old way → insight → mechanism → product link → loop | Roomba cliff sensing (US 6,883,201) |
| **The patent behind the news** | this week's story → the question it raises → the patent → how it works → why it matters now | a product launch, a recall, a lawsuit in the news |
| **The weird drawing** | a strange patent figure → "what is this?" → reveal → how it works → where you have seen it | odd figures from everyday patents |
| **Expired, now everywhere** | the thing everyone has → it was once one company's → the patent → expiry date → what happened next | LEGO brick (1958), cheap 3D printers after FDM expiry |
| **Kitchen and home** | an everyday object → the hidden problem it solves → the patent → the clever bit | appliances, packaging, tools |
| **Software you touch** | an on-screen moment → what is happening invisibly → the patent's method → what it means for you | the iPhone keyboard's invisible key targets (US 8,232,973) |

**Default beat spine** (How it works, 60–70 s, 110–170 words at about 2.5 words a second): hook (0–3 s, works muted) → problem (from the patent's background) → the old way (background and cited references only) → the insight in one sentence (checked against claim 1) → mechanism, one worked example → product link and impact, with the honest caveat → loop-back line that calls the first frame.

## 5. The ledger (research output)

One `ledger.json` per episode. The writer may use only what is in it.

- **Patent:** number, title, assignee, inventors, priority, filing and grant dates, Google Patents URL.
- **Status:** "granted <date>"; "expired" or "active" only with a dated USPTO maintenance-fee or Patent Center check (URL, date); otherwise status stays unstated.
- **Copyright check:** notice present at the start of the specification or under figures? (if yes: no figure use, redraw nothing from it).
- **Claims:** claim 1 paraphrase with its location; key terms defined.
- **Story facts:** problem, old way, insight, mechanism steps, each with a location (column/paragraph or claim) or a URL.
- **Product link:** phrasing-ladder level 1–4 with its evidence (marking page URL and date, company statement, teardown).
- **Visual material:** patent figures worth redrawing (figure numbers), product shape references we may draw from, openly licensed images (URL, licence, author), what could be filmed by the owner.
- **Risks:** litigation, contested origin, sensitive topics; anything uncertain is labelled "inferred".

## 6. Facts and rights rules

- **Phrasing ladder** (`RESEARCH.md` §5): the script may claim only up to the level its evidence supports. "Ships in" needs level 4. Never "invented", "first" or "revolutionary" unless sourced. Never legal advice; "granted" is not "valid".
- **Images:** the product can look exactly like itself. Sources, in order: our own builds (coded, 2.5D or 3D) · the owner's own photos and video · openly licensed images and models with a recorded licence and credit (CC0, public domain or CC BY; **not** CC BY-SA, whose ShareAlike terms conflict with platform terms once we crop or overlay, unless the standards editor clears that exact use; never NC or ND) · our redraws of patent figures. Never company press renders, marketing images or ads, or images found by search. No logo as a title graphic, no implied endorsement; every caption that names a company says "Not affiliated with or endorsed by <company>." Every asset is listed in `assets.json` (role, source, licence, author) and credited in `render.json`.
- **Patent figures:** US patents with no copyright notice; redrawn as our own motion graphics, cited on screen ("US 6,883,201, Fig. 3").
- **Voice:** a neutral AI narrator, never presented as a human expert, no avatar. `render.json` discloses the synthetic voice; platform AI labels follow the contract module.
- **Standards editor's list:** phrasing ladder respected · status claims dated · images within the source order · no logo misuse or endorsement · caption has the not-affiliated line · AI disclosure set · no legal, medical or financial advice · names of people only as public record (inventors, assignees) · sensitive news topics (deaths, disasters, crime) never used as a trend hook.

## 7. Visual system

- **Scene catalog** in `engines/motion/src/projects/explainers/scenes/<id>/`: `Scene.tsx`, `schema.ts` (Zod props), `card.md` (intent, parameters, pitfalls, preview still). The art director's menu is generated from the catalog, so it can only pick scenes that exist. A new scene ships only after a pitch (beat, line, idea, why the catalog fails) and approved stills, and must be reusable in at least 2 future episodes.
- **First cards:** hook card · patent stamp (number, title, assignee, date) · figure trace (redrawn figure drawn on with `@remotion/paths`, callouts) · claim highlight · problem vs fix split · mechanism (parts with motion paths) · exploded layers (2.5D first, `@remotion/three` later) · timeline (filed → granted → product → expiry) · big number · product shot (licensed photo or our model, slow push) · verdict · loop end.
- **Beat spec** (`beats.json`, Zod-validated, fails loudly): per beat the scene id and props, the word range it spans (start/end word ids), on-screen banner (≤ 5 words, one fact the voice does not repeat), the source decision (reuse / adapt / coded diagram / kinetic type / new scene) with the options that lost, motion notes, sound cue, fact references into the ledger.
- **Layout:** 1080×1920, stage units on a 12-column grid, safe zones (150 px top, 170 px bottom, 60 px sides), type floor (headline ≥ 56 px, body ≥ 36 px), text fitted with `@remotion/layout-utils`; patent numbers and dates never wrap. A layout check renders a still at each beat midpoint and fails on overlap, clipping or a safe-zone breach before the critic sees anything.
- **Captions:** word-by-word from `words.json` with `@remotion/captions`; they never cover the banner or a figure callout.
- **Brand:** `projects/explainers/brand/` (`brand.md`, `MOTION.md`, `voice.md`). Banned defaults: centred title on a gradient, everything fading in, glow, typewriter text, generic particles, two type-only beats in a row, Inter-on-purple "AI look", rounded card grids, stock footage as the hero.
- **Audio:** music bed (light, CC0, ducked well under the voice), procedural SFX on beats, mastered by the existing chain (−14 LUFS, true peak ≤ −1 dBTP).

## 8. Voice and timing

1. **Lint** the locked script: hook length, numbers written for speech, pronunciations for jargon and names (`brand/pronunciations.json`), line length.
2. **TTS:** Gemini Flash TTS on the free tier with one chosen voice and a style prompt from `brand/voice.md`; one request per episode, cached by script hash. Key `GEMINI_FREE_API_KEY` from a Google project **without billing**, read only by this tool.
3. **Transcription check:** `@remotion/install-whisper-cpp` (local) transcribes the take; words that do not match the script trigger a retry (at most 3), then a flag.
4. **Alignment:** whisper tokens merged into words and matched to the script's words → `words.json` (Remotion `Caption` type). Scenes start and end on word ids; the episode length comes from the audio (`calculateMetadata`).
5. **Fallback:** Kokoro-82M on the Mac if the free tier changes. A silent placeholder with even word spacing lets visuals be built before the voice, never shipped.

## 9. Trend scout

- **Fetch** (`projects/explainers/tools/scout_feeds.py`, stdlib, once per batch): Google Trends "Trending now" RSS (US), Hacker News top and best stories, Wikimedia top pageviews (junk pages filtered), GDELT article lists for a few queries (patent, patent lawsuit, product launch, product recall, new invention). Identifying User-Agent with the repo URL; titles, links and counts only; cached to `library/<batchId>/review/scout.json`.
- **Think** (scout agent): cluster the items, drop anything without a technical or product hook and any sensitive story, name the product, company or practice behind each, and find a patent angle: company patent-marking pages, individual Google Patents pages (allowed; never its search URLs), web search. Score each on surprise, everyday relevance, how visual it is, evidence strength and freshness; check the done list so nothing repeats.
- **Not used:** Google News RSS (licensed for personal, non-commercial readers only), Reddit, TikTok, Product Hunt, Exploding Topics (terms or cost); USPTO PatentsView (shut down).
- **Later:** BigQuery patent search (free tier) for keyword and CPC search; EPO OPS for families and status.

## 10. Packaging, contract, publishing

- **render.json** per episode (`tools/RENDER_JSON.md`): credits for every asset (patent figures redrawn, licensed images with attribution, CC0 music, generated voice), disclosure for the synthetic voice, renderer `render.sh`.
- **Captions** per platform: the hook as a line · one sentence of payoff · `Patent: US X,XXX,XXX · <assignee> · <year>` · "Not affiliated with or endorsed by <company>." · a question to end ("Which product should we open next?") · 3–5 hashtags. Sources in the YouTube description (or first comment where supported). No link.
- **Contract module** `contract/projects/explainers.py` (contract change, owner approval): requires the patent line, the not-affiliated line when a company is named, the disclosure, and every attribution a licence requires in the text that posts.
- **Publishing:** the explainers lane (`PLAN.md` §4) posts one a day on each platform at its own time; the autopilot refills it on its own runway.

## 11. In the Pi UI

- **Studio › Make a batch:** Explainers appears next to Scalargame and Originals. Fields: batch id, episode count (default 7), formats, subjects (optional: patents or topics, one per line; empty means the scout picks), trend scout on/off, notes. It copies the `/explainer brief <batchId>` prompt with the safety lines, and lists the checkpoints for the batch. Nothing is generated on the Pi.
- **Studio › Overview:** an Explainers card with runway, last batch and next batch due date.
- **Schedule:** the explainers lane alongside Scalargame's.

## 12. Files

```
projects/explainers/
  PLAN.md  SYSTEM.md  RESEARCH.md
  project.json  package.mjs  package-core.mjs
  brand/      brand.md  MOTION.md  voice.md  pronunciations.json
  formats/    formats.json (spines, limits; read by the checker)  formats.md (cards, hook types)
  tracks/     patents.md (backlog, done list, scout weights)
  tools/      scout_feeds.py  check_episode.py (ledger + script lint)  tests/
engines/motion/src/projects/explainers/
  ExplainerEpisode.tsx  layout.ts  captions.tsx  schema.ts (beats)
  scenes/<id>/  Scene.tsx  schema.ts  card.md
engines/motion/pipeline/explainers/
  lint · voice · align · props · layout-check · render (wraps render.sh, writes render.json)
.claude/skills/explainer/   SKILL.md
.claude/agents/             explainer-{trend-scout,patent-researcher,story-writer,fact-checker,standards,cold-reader,art-director,critic}.md
contract/projects/explainers.py  (+ tests)
library/<batchId>/          batch.json (the only tracked file)  review/ (ignored: state, scout, slate, jobs/<ep>/…)
library/_briefs/<batchId>.md  library/_retros/<batchId>.md   (tracked notes)
```
