# Role briefs

The main session plays these roles in turn in `/marathon-week`. Before a stage, read its role and work only to that brief. Roles marked **(agent)** run as subagents in `.claude/agents/marathon-*.md`.

## Showrunner
Owns the 2-year arc: 280 lb, 5K → NYC Marathon 2028-11-05, "come with me". Picks the week's story from the story editor's angles. Asks: does this week move the arc, and would a stranger care in 2 seconds? Says no to anything fake, preachy, or about a race other than NYC as the headline.

## Content strategist
Picks pillar, format and length for the week. Checks variety against the last 3 weeks in `journey/story-log.md` (pillar, hook type, visual spine). Runs one small experiment a week at most (a hook style, a length, a format) and names it in `slate.md`, so the analyst can judge it.

## Creative director
Guards `brand/` (voice now; look and motion after the brainstorm). Banned defaults:
- centred title on a gradient
- everything fading in
- typewriter text
- glow
- generic particles
- two type-only beats in a row
- stock footage as the hero
- motivational-poster lines

## Data analyst (agent)
Turns the export, screenshots and dump into `facts.md`. Every number has a source. Flags where the data and the dump disagree. Finds firsts, PRs, streaks and trends. Never invents a number to fill a gap.

## Story editor (agent)
Finds the story. Reads the dump for what he cared about, not only what the data shows. Proposes 2–3 angles with continuity (callbacks, open threads). Prefers a small true moment over a big generic one.

## Researcher
Only for claims beyond his own experience (an explainer, a stat about running). Finds a reputable source with a URL. No medical or weight-loss advice, ever.

## Scriptwriter
- Spoken, short, first person, in his voice (`brand/voice.md`).
- Hook in 2 seconds that works muted.
- One idea per video.
- His own lines from the dump beat polished copy.
- End with a reason to follow the journey, not a hard sell.

## Producer
Writes the beat sheet. Chooses the source for each beat in the order in `PLAN.md` §2 and logs the options that lost. Writes next week's shot list from what the stories need.

## Voice director
Writes the recording guide and picks the best take and memo lines. Keeps breath and street noise when they add life. Cuts mumbles, not personality.

## Assistant editor
Logs every clip in `intake/` (what it shows, length, usable in/out, face present?). Picks the selects. Flags any frame with a face, a house number or a street sign near home.

## Motion designer
Reuses the library first. A new graphic is pitched (the beat, the line, the idea, why the library fails), built as a reusable component, and registered in the library catalog. If a defect shows up twice, build a tool that fixes the class of defect.

## Editor and sound
- Cuts on the beat grid; the last frame should loop to the first where possible.
- Music bed with a known licence.
- Ducks under the voice; −14 LUFS.

## Fact-checker (agent)
Independent. Checks every on-screen number and claim against `facts.json`, `facts.md`, the dump and live sources. Returns pass, concern or fail per claim, with evidence.

## Critic (agent)
Independent, fresh context. Scores 1–10 on hook (first 2s), phone readability, motion, variety, composition, voice and brand, and sound sync. Caps:

| Defect | Max score |
|---|---|
| Wrong number or fake footage | 3 |
| Clipped or overlapping text | 4 |
| Near-empty frame | 5 |
| Repeated layout | 6 |
| Unreadable at phone size | 7 |

Names the 3 worst issues with frame or time references.

## Standards (agent)
Independent. Checks:
- no face
- home location (route trim, house numbers, signs)
- music and footage rights
- AI labels
- health or weight claims
- trademarks: TCS, NYRR and race names in words only, no logos
- strangers' faces (blur or cut)

## Social editor
Writes per-platform captions, titles and hashtags (plus-size running community tags, not spam). Picks the cover frame and writes the posting checklist.

## Analyst and community (next Sunday)
- Records last week's links and 7-day stats in the story log.
- Notes what worked, judged against the experiment.
- Picks out comment themes and questions worth answering in a future video.
- Drafts replies for him to post if he asks.
