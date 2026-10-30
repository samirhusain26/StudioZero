# Marathon plan

Started 2026-10-12. Status: **set up; the brainstorm session is next** (§7).

## 1. Decisions (owner, 2026-10-12)

- **The story:** "Come with me": a 280 lb, plus-size runner who can run a 5K today, on the way to the NYC Marathon on 2028-11-05. The marathon is the only race the channel anchors on. The Jersey City Half (April 2027) and the NYRR 9+1 races (2027) are chapters, not the headline.
- **Entry:** the owner is in the 2027 NYRR 9+1 program (nine qualifying races plus one volunteer shift → guaranteed, paid 2028 entry). Q1 race picks are submitted; nothing is paid yet.
- **Channels:** new Instagram, TikTok and YouTube Shorts accounts. **Posted by hand.** No automation, no StudioZero publisher for now.
- **Cadence:** **one video a week**, made every **Sunday**. More only if it gets traction.
- **On camera:** no face. Body, feet, legs, hands, POV and surroundings are welcome, so the channel stays human. Not anonymous: name, bibs and results may show.
- **Voice:** his own voice, for raw post-run memos and/or scripted voiceover; still deciding.
- **Input:** every video starts with **the dump**: a free-form brain dump of the week (what he did, what he felt, what is on his mind) plus whatever data he has. The training plan changes weekly, so the dump is the source of truth, not a plan file.
- **Moved into StudioZero** (owner, 2026-10-13; it started as a separate repo on 2026-10-12) as `projects/marathon/`, so every video-generation asset, skill and tool lives in one repo. Still posted by hand: it is a `manualProjects` entry in `studio.json` whose `project.json` feeds a prompt card on the Pi's Studio › Overview; no batches, contract module, publisher channels or autopilot until automation matters.

## 2. Content rules

The hard rules in `README.md` apply.

**Source order for every beat (moment) of a video.** Take the first option that fits, and log the options that lost:

1. a reusable graphic from our library
2. an adapted library graphic
3. his real footage or voice
4. a data graphic: route line, pace, heart rate, mileage, countdown, 9+1 tracker, weight if he chooses
5. kinetic type
6. a new coded graphic (pitched, reusable)
7. a non-realistic AI illustration (labeled)
8. ambient AI video (rare, labeled)
9. ambient stock footage, never the hero

## 3. The team

A professional studio would staff these roles end to end. At one video a week, Claude plays most of them in sequence inside the `/marathon-week` skill (briefs in `.claude/skills/marathon-week/roles.md`). Five run as **subagents** with a fresh context, because their job is to judge work the main session wrote, or to work independently.

| Stage | Role | Job | How |
|---|---|---|---|
| Direction | Showrunner | Keeps the 2-year arc; picks the week's story; final say before the owner | main session |
| | Content strategist | Pillar and format for this week, variety over the last weeks, experiments | main session |
| | Creative director | Brand, look and motion rules; banned defaults | main session; `brand/` |
| Development | **Data analyst** | Reads the Health export and screenshots; computes the week; finds PRs, streaks, firsts | **subagent** + `tools/health_export.py` |
| | **Story editor** | Finds the story in the dump and the data; proposes angles; continuity with `journey/story-log.md` | **subagent** |
| | Researcher | Sources for any explainer claim | main session |
| Pre-production | Scriptwriter | Hook (works muted), voiceover lines, on-screen text, word budget | main session |
| | Producer | Beat sheet with a source decision per beat (§2); shot list for next week | main session |
| | Voice director | Recording guide for his VO; picks memo lines | main session |
| Production | Assistant editor | Logs his clips; picks selects | main session |
| | Motion designer | Builds and reuses graphics; keeps the library catalog | main session (renderer TBD) |
| | Editor and sound | Assembles the cut; music bed, SFX, loudness | main session |
| Quality | **Fact-checker** | Every on-screen number against `facts.json` and the dump; explainer claims against live sources | **subagent** (read-only) |
| | **Critic** | Scores contact sheets and phone-size frames on a capped rubric; gives frame numbers | **subagent** (read-only) |
| | **Standards** | Face, home location, rights, AI labels, health claims, trademarks (NYRR/TCS by name only, no logos) | **subagent** (read-only) |
| Distribution | Social editor | IG/TikTok/YT captions, title, hashtags, cover frame, posting checklist | main session |
| | Owner | Posts by hand; pastes links and stats back | owner |
| Learning | Analyst and community | Last week's stats and comments → what worked → `journey/story-log.md` | main session, next Sunday |

## 4. The Sunday flow (`/marathon-week <YYYY-Www>`)

| # | Stage | Output | Owner |
|---|---|---|---|
| 1 | **Dump**: brain dump, Health export or screenshots, clips, memos; last week's stats | `dump.md`, `intake/` | talks for 5–10 min, drops files |
| 2 | Data | `facts.md`, `facts.json` | |
| 3 | Story: 2–3 angles, continuity, last week's learnings | `story.md` | |
| 4 | Slate: this week's video (what it is about, pillar, length, hook options, the footage it uses) | `slate.md` | **Checkpoint 1: pick the angle** |
| 5 | Script: VO and/or on-screen text; sources | `script.md` | **Checkpoint 2: lock the script** → records VO if used |
| 6 | Beats: one row per beat with timing, text, VO line, source decision, data source, sound cue | `beats.md` | |
| 7 | Build: render (renderer TBD) | `render/` | |
| 8 | Review: critic, standards and fact-checker; fix the worst issues; repeat | `review.md` | |
| 9 | Package: captions per platform, cover, next week's shot list | `publish.md` | **Checkpoint 3: final cut** → he posts |

## 5. Pillars (first cut; the brainstorm decides)

1. **The week:** what happened, in numbers and feelings; the countdown.
2. **Firsts and PRs:** first 10K, longest run, first race, 9+1 race N of 9.
3. **Running big:** chafing, gear that fits, pace shame, being passed, being cheered, the scale (if he wants it on screen).
4. **What I learned:** fact-checked explainers (zone 2, run-walk, fueling, rest).
5. **The road to NYC:** 9+1 progress, the volunteer day, the bib.
6. **The quiet ones:** 5 a.m., rain, a bad run told honestly.

## 6. Data

- **Apple Health export** (Health app → profile picture → Export All Health Data). `tools/health_export.py` reads `export.zip` or `export.xml` for a date range: running workouts, distance, time, pace, heart rate, elevation, mile splits from the route file, and a trimmed route line for drawing.
- **Screenshots** of the Fitness app work too; the data analyst reads them when no export is given.
- Not the Strava API: its terms restrict display and forbid AI use of API data.

## 7. Next session: brainstorm

Start with: "Read projects/marathon/README.md and PLAN.md; run the brainstorm."

1. **Channel name and handle.** Seeds:
   - 280 to 26.2
   - Big Guy Long Run
   - Heavy Miles
   - Plus Size Pace
   - The Long Way to NYC
   - Pounds to Pavement
   - 26.2 at 280
   - Slow & Steady to NYC

   Check availability on all three platforms.
2. **The look:** 2–3 reference videos he likes; colours, type and motion rules (`brand/brand.md`, `brand/MOTION.md`); banned defaults.
3. **Voice:** finish `brand/voice.md`. What "plus-size runner" means in his words; is weight on screen or not; how to handle trolls.
4. **Formats and pillars:** the recurring weekly format, the first 8 weeks (to mid-December), and the channel trailer/intro video ("Day 1: I'm 280 lb and I'm going to run NYC").
5. **Renderer:** Remotion (proven in StudioZero) or another; then build the first graphics (week card, countdown, route line, 9+1 tracker).
6. **The shot kit:** what to film on runs this week (phone mount, angles, feet, watch, breath), so next Sunday has footage.

## 8. Open items

- Channel name and handles (brainstorm).
- Voiceover style (memos, scripted, or both).
- Weight on screen: yes or no, and how often.
- Renderer choice and the first graphics kit.
- Music: CC0 beds (StudioZero has 134 CC0 tracks with recorded licences), or the platforms' in-app sounds added when posting by hand.
