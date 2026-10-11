// Question pack prose for set questions-2026-10 (batches 2026-10-pilots and 2026-10-b01), kept verbatim so
// `pack.mjs --set=questions-2026-10` reproduces the historical Checkpoint 1 pack byte for byte. New batches do not
// need a file like this: pack.mjs has generic defaults, and CONFIG.pack may override any of these fields.
export const PACK_2026_10 = {
  title: '2026-10',
  intro: ({doc}) => `Checkpoint 1. 24 questions (6 per game, 3 approachable / 2 moderate / 1 challenging, 3 per format) plus ${doc.questions.filter(q => q.spare).length} spares, four marked as pilots. Nothing is rendered yet.`,
  snapshotNote: ' (committed HEAD only; uncommitted game-repo edits such as Taiwan and the Canada area fix are excluded)',
  checksNote: '',
  sourceCheckNote: ' All five concerns are resolved in this pack (see each card); one replacement question was verified by the main session.',
  notes: ({doc, cand, esc}) => `
<h2>Checkpoint 1 decisions (6 Oct 2026)</h2>
<div class="ask"><b>Answered:</b> burn A/B/C choices + “Comment your letter” into the videos · music: Scalar 6, Continuum 2, Whenabouts 5, Tectonic 3 (beds built: <code>engines/motion/public/episodes/music/beds.json</code>) · style recipes: all four recommended · Whenabouts: “Do not worry about spoilers” (the strict ended-Daily rule is waived; the Whenabouts set was rebuilt from the full event pool and re-verified) · the monthly <code>com.scalar.social.replenish</code> job is unloaded, plist parked in <code>~/Library/LaunchAgents/disabled/</code>.<br><b>Still open:</b> approval of these questions; the contract spoiler-gate change below (publishing side).</div>
<h2>Original questions (for reference)</h2>
<div class="ask"><h4>1 · Burn A/B/C choices and a “comment your letter” prompt into the videos?</h4>
Recommended: <b>yes</b>. Choices appear only after the last clue (never with the first clue), stay on screen through the thinking window, and the prompt “Comment your letter” sits under them during the think window only. This makes muted viewing a complete quiz and matches the caption/poll plan. Alternative: choices in captions only, videos stay open-answer.</div>
<div class="ask"><h4>2 · Music</h4>Owner-supplied tracks in <code>engines/motion/music/sources/</code> (all 120 BPM, Gemini-generated, reuse authorized by you on 28 Sep and 5 Oct; no independent licence verification). Track 4 “Guess It, Place It” is sung, so it is excluded by the instrumental rule.<br>
Recommended mapping: <b>Scalar → 6</b> “Skipping Downstairs” (pluck, light) · <b>Continuum → 2</b> “Midday Market Rush” (funk) · <b>Whenabouts → 5</b> “Golden Question” (game show, clock ticks) · <b>Tectonic → 3</b> “The Pocket Heist” (electro-pop with a riser/drop for the snap). Track 1 “Big Prize Reveal” as alternate. Each bed is cut on the beat grid so the reveal lands on a downbeat, quieter under the thinking window, −14 LUFS / −1 dBTP.</div>
<div class="ask"><h4>3 · Style recipe for each game (batch 2026-10)</h4>
<table><tr><th>Game</th><th>Recommended</th><th>Alternative</th></tr>
<tr><td>Scalar</td><td><b>scalar-notebook-1</b> · paper #FAFAF9, charcoal ink, teal accent, thermal green/orange; Fraunces 900 + Geist Mono; clues are index cards dealt onto a desk; a live “countries left” counter (195 → 39 → 6 → 1) uses the real candidate counts; reveal = green stamp + locator map of the answer.</td><td><b>scalar-survey-1</b> · night slate #0F172A, teal HUD lines, monospace, radar sweep between clues.</td></tr>
<tr><td>Continuum</td><td><b>continuum-poster-1</b> · cream #F7F3EC, black, hot pink #F472B6; Montserrat 800 + IBM Plex Mono figures; honest bars from a labelled zero baseline (same scale per video), a vertical ranking ladder with three insertion gaps for missing-slot.</td><td><b>continuum-neon-1</b> · black, pink/cyan glow bars.</td></tr>
<tr><td>Whenabouts</td><td><b>whenabouts-almanac-1</b> · parchment #F4ECD8, sepia ink, yellow #EAB308; Fraunces italic headlines; a horizontal ruler timeline that pans; reveal = year odometer rolling to the answer; typographic event card with vector ornament (no photos).</td><td><b>whenabouts-museum-1</b> · white gallery wall, black serif museum labels, small caps.</td></tr>
<tr><td>Tectonic</td><td><b>tectonic-ocean-1</b> · deep navy ocean with depth gradient, warm orange land #F2A154, muted sand neighbors, Nunito 900; canonical globe geometry in orthographic projection centred on the target; neighbors drift in, the gap pulses with a dashed edge, the answer piece drops in with a spring and the camera pulls back to continental context.</td><td><b>tectonic-atlas-1</b> · cream paper atlas, ink outlines, cross-hatching.</td></tr></table>
Branding is subtle in every recipe: small “SCALARGAME · &lt;GAME&gt;” label top-left inside the safe area; closing card “Play a new puzzle · scalargame.com”. No personal creator credit.</div>
<div class="ask"><h4>4 · Whenabouts freshness (your call)</h4>
I applied the strict rule: an event may appear only if <i>every</i> Daily it belongs to has ended (UTC−12 + 4-day buffer). Only ${cand.whenabouts.endedEvents} of ${cand.whenabouts.events} events qualify, because events recur in future Dailies through 2029 (the Moon landing, Eiffel Tower, Magna Carta, Wright brothers all reappear). The pack above uses only those. Keep strict (recommended, and what the plan says), or authorize a relaxed rule for later batches, for example “next Daily appearance more than 12 months away”. A posted video stays visible, so any relaxation means accepting a minor spoiler on one of the five events in a future Daily.</div>
<div class="ask"><h4>5 · Contract issue for the publishing side (no change made)</h4>
BATCH_CONTRACT.md's spoiler gate says no caption, first comment or poll question may contain the answer, but its own example caption and <code>firstComment</code> list the choices (“A) Bolivia B) Paraguay…”), which contain the answer. Every choice-bearing caption would fail a literal gate. Also, the answers to before/after (“Before”/“After”) and missing-slot (“Between”) are ordinary words that appear in the question itself. Proposed contract change: the gate ignores the exact canonical choices block (<code>A) … B) … C) …</code>) and <code>poll.options</code>, and for formats whose answer is a choice word it checks the answer <i>key reveal</i> (e.g. “Answer: B”) rather than the bare word. Needs your approval and the publishing session's validator; I won't write my own.</div>
<div class="ask"><h4>6 · Monthly Mac job <code>com.scalar.social.replenish</code> (conflicts with D23)</h4>It is loaded (next run 1 Nov 03:00) and would render 35 legacy-format episodes. To stop it without deleting anything:
<pre>launchctl bootout gui/$(id -u)/com.scalar.social.replenish
mkdir -p ~/Library/LaunchAgents/disabled
mv ~/Library/LaunchAgents/com.scalar.social.replenish.plist ~/Library/LaunchAgents/disabled/</pre>
Reversible with <code>mv</code> back + <code>launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.scalar.social.replenish.plist</code>. May I run these?</div>
<div class="ask"><h4>7 · Pilots</h4>Proposed pilots (one per game, the first format of each): ${doc.questions.filter(q => q.pilot).map(q => `<b>${esc(q.key)}</b>`).join(', ')}. The other four templates will be previewed as still frames in the pilot review sheet.</div>

<h2>Episode structure and the eight templates</h2>
<p>Common sequence: hook → information → thinking window (≥ 6 s, all required information on screen) → reveal → explanation → invitation. 30 fps, 120 BPM grid (one bar = 2 s) so reveals land on downbeats. Safe rectangle x 90–900, y 270–1530; the CTA sits inside it.</p>
<table><tr><th>Template</th><th>Length</th><th>Information complete</th><th>Think</th><th>Reveal / explain / CTA</th></tr>
<tr><td>Scalar progressive clues</td><td>24 s</td><td>clues at 1.5 / 3.5 / 5.5 s, choices at 7.0 → complete 8.0 s</td><td>8.0–14.5</td><td>reveal 14.5 (stamp + locator) · explain 17.5 · CTA 21.5–24</td></tr>
<tr><td>Scalar candidate elimination</td><td>24 s</td><td>three candidates 1.5 s, clues 3.0 / 4.75 / 6.5 → 7.5 s</td><td>7.5–14.0</td><td>clues strike out candidates in order 14.0–17.0 · explain 18 · CTA 21.5</td></tr>
<tr><td>Continuum head-to-head</td><td>20 s</td><td>question + A/B cards 0–3.5 s</td><td>3.5–10.0</td><td>bars grow to true values 10.0–13.0 · explain 13.5 · CTA 17.5–20</td></tr>
<tr><td>Continuum missing slot</td><td>22 s</td><td>ladder with two anchors (values hidden), target card, three slots → 6.0 s</td><td>6.0–12.5</td><td>target drops into its slot, values reveal 12.5–16 · explain 16.5 · CTA 19.5–22</td></tr>
<tr><td>Whenabouts guess the year</td><td>22 s</td><td>event card 0–3 s, three years on ruler → 5.5 s</td><td>5.5–12.0</td><td>odometer rolls to the year, ruler marks it 12.0–15.5 · explain 16 · CTA 19.5–22</td></tr>
<tr><td>Whenabouts before / after</td><td>22 s</td><td>event card, anchor pinned on timeline (year shown), Before/After → 6.0 s</td><td>6.0–12.5</td><td>event slides to its side, both years shown 12.5–16 · explain 16.5 · CTA 19.5–22</td></tr>
<tr><td>Tectonic missing country</td><td>22 s</td><td>neighbors assemble around the gap (labels on), choices → 6.0 s</td><td>6.0–12.5</td><td>answer piece drops and snaps 12.5–15.5, pull-back to context · explain 16.5 · CTA 19.5–22</td></tr>
<tr><td>Tectonic neighbor clues</td><td>24 s</td><td>neighbor shapes + names one at a time 1.5 / 3.0 / 4.5 s (schematic, no implied positions), choices → 7.0 s</td><td>7.0–13.5</td><td>map assembles in true positions, target fills with shared borders highlighted 13.5–17.5 · explain 18 · CTA 21.5–24</td></tr></table>
<p>Muted completeness: every cue is visual (clue counter, think bar, stamps, labels). SFX are purposeful and quiet: card/piece placement, one think-start tone, a reveal hit on the downbeat; no ticking countdown. Covers are spoiler-free stills of the question state (no answer, no recognisable answer outline).</p>

<h2>Proposed asset kit (kit-1)</h2>
<pre>engines/motion/src/episodes/
  LibraryEpisode.tsx         one composition; props = resolved episode + style recipe + audio cue sheet
  Cover.tsx                  spoiler-free cover still
  kit/manifest.json          asset IDs, versions, hashes, sources and licences (fonts OFL, geometry Natural Earth, music owner-supplied)
  kit/brand.tsx              Scalargame wordmark, game label, closing CTA card
  kit/fonts.ts               Fraunces, Geist Mono, Montserrat, IBM Plex Mono, Nunito (OFL, bundled locally)
  kit/safe.ts, timing.ts     safe rectangle + per-template timelines; asserts the ≥6 s thinking window at build time
  kit/motion.ts              easing/spring presets, enter/exit and stamp primitives
  kit/Choices.tsx, Think.tsx A/B/C chips, “comment your letter”, calm progress bar
  kit/sfx.ts                 SFX cue sheet → audio track (existing procedural public/sfx)
  kit/geo/                   projection of canonical globe rings, CountryShape, regional frame, locator inset
  kit/chart/                 Bar (zero baseline, labelled scale), Ladder (ranking with slots)
  kit/time/                  Ruler timeline (BCE/CE, no year zero), Odometer
  styles/&lt;styleId&gt;.ts        one recipe per game per batch (palette, type, layout, motion, reveal)
  templates/                 the eight format templates
engines/motion/public/episodes/fonts, music/ (cut beds; TRACKS.md in engines/motion/music/)
engines/motion/pipeline/     snapshot → candidates → check → pack → episodes (immutable inputs) → render (per-episode resumable jobs via engines/motion/render/render.sh) → batch (batch.json + captions) → review sheet
library/&lt;batchId&gt;/           videos/, covers/, batch.json, review/ (jobs, frames, probe, validator output)</pre>
<p>Captions, YouTube title/description, alt text, hashtags, poll and first comments are deterministic templates filled from each episode's metadata, spoiler-free, with <code>{link}</code> only on Facebook, Threads, X and Bluesky. <code>answerReply</code> stays null.</p>

`,
};
