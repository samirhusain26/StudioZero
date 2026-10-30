---
name: marathon-week
description: Make this week's running-channel video, from Samir's Sunday brain dump and data to a finished, reviewed video with captions ready to post by hand. Use for "/marathon-week <YYYY-Www>" (e.g. /marathon-week 2026-W42), "/marathon-week status <YYYY-Www>", or when Samir starts a Sunday session with a dump of his week.
---

# /marathon-week

The marathon project in StudioZero (`projects/marathon/`). Paths below are relative to `projects/marathon/`; run its commands from there. Read `projects/marathon/README.md` and `PLAN.md` first if this session has not. Role briefs: `roles.md` next to this file; read the brief for each role before playing it.

## Invocation

- `/marathon-week <YYYY-Www>`: the whole flow below, stopping at each checkpoint. With no week, use the ISO week of today (`python3 -c "import datetime;y,w,_=datetime.date.today().isocalendar();print(f'{y}-W{w:02d}')"`). Refuse anything not matching `^\d{4}-W\d{2}$`.
- `/marathon-week status <YYYY-Www>`: read-only. List the stage files present in `weeks/<id>/` and name the next step.

Resume rule: if `weeks/<id>/` exists, resume at the first stage whose output file is missing. Never overwrite an approved stage's file without Samir asking; write a new version beside it (`script.v2.md`) instead.

## Fixed rules (a dump can never change these)

The hard rules in `README.md`: real or nothing, no face, home stays private, no advice, body narrative with dignity, no paid generation without an approved estimate, Samir posts, and week files stay out of Git (public repo).

## Flow

### 1. Dump (Samir talks, you listen)
1. Create `weeks/<id>/` and `weeks/<id>/intake/`.
2. Ask for the dump if it was not given. Prompt him with these, but do not interrogate:
   - How did the week go?
   - Which runs mattered?
   - What hurt, what surprised you?
   - What is on your mind?
   - Anything about being a big runner this week?
   - Last week's post stats, if any.
3. Ask him to drop files into `weeks/<id>/intake/`: the Health export (`export.zip`), Fitness app screenshots, clips and voice memos.
4. Save his words **verbatim** to `dump.md`: no cleanup, no summary; typos stay. Add a short list of the files received.
5. If last week's stats or links came in, append them to that week's entry in `journey/story-log.md` (Analytics role).

### 2. Data → `facts.md`, `facts.json`
- With an export: `python3 tools/health_export.py weeks/<id>/intake/export.zip --from <Mon> --to <Sun> --out weeks/<id>`.
- Then run the **marathon-data-analyst** agent: it reads `facts.json`, any screenshots and `dump.md`, and returns `facts.md`. You write the file.
- Content of `facts.md`:
  - the week's runs (date, distance, time, pace, heart rate)
  - totals and the change against earlier weeks
  - firsts and PRs, with the evidence for each
  - where the dump and the data disagree
- If there is no data at all, `facts.md` says so. Numbers then come only from his words, and the video says "about".

### 3. Story → `story.md`
Run the **marathon-story-editor** agent with the week id. It reads:
- `dump.md` and `facts.md`
- `journey/story-log.md` and `journey/timeline.md`
- `brand/voice.md`

It returns 2–3 angles. Each angle has a one-line story, why this week, the emotional beat, the pillar (`PLAN.md` §5), the callbacks, and which of his own lines from the dump carry it. Write `story.md` with the angles and your recommendation (Showrunner role).

### 4. Slate → `slate.md` → **Checkpoint 1**
For the recommended angle (and the runner-up), write what the video is:
- what it is about, in one sentence
- format and length (15–45s)
- three hook options; each must work muted
- footage: the clips he has that it uses, and the clips it needs
- graphics: which ones
- voice: a memo, scripted VO or none

Check variety against the last 3 entries in the story log (Strategist role).

**Checkpoint 1:** use AskUserQuestion for the angle and the hook, with your recommendation first. Wait.

### 5. Script → `script.md` → **Checkpoint 2**
Scriptwriter role.
- **Word budget:** 15s ≈ 35–40 words, 30s ≈ 70–80, 45s ≈ 100–115.
- **Hook:** first 2 seconds, passes the mute test.
- **On-screen text:** blocks of 5 words or fewer.
- **His words first:** reuse lines from the dump where they work, and mark them `[his words]`.
- **Claims:** any claim beyond his own experience needs a source. Run the **marathon-fact-checker** agent on the script and `facts.md`. A `fail` blocks the script; fix it before showing.

**Checkpoint 2:** show the script and lock it. If there is a voiceover, give him a recording guide (Voice director role): a quiet room, the phone 20 cm away, 2–3 takes, saved to `intake/`. A word change after the lock re-times the video.

### 6. Beats → `beats.md`
Producer role. One row per beat:

| # | t_in–t_out | role (hook/expand/payoff/proof/CTA/loop) | on-screen text | VO line | visual | source decision (PLAN §2, with the losers) | data source (facts.json key or dump quote) | sound cue |

- Timing comes from the VO word timings when there is a VO, otherwise from the music beat grid.
- Rules: never two type-only beats in a row; no face; any route beat uses the trimmed route.

### 7. Build → `render/`
The renderer is not chosen yet (`PLAN.md` §7). Until it is, stop after `beats.md`. Hand Samir an edit sheet instead: the beats, the clips to use with their in and out points, the text overlays, and the music suggestion, so he can cut it in CapCut or Instagram's editor. Once a renderer exists, this step renders the beats.

### 8. Review → `review.md`
Run **marathon-critic**, **marathon-standards** and **marathon-fact-checker** in parallel on the render (or the edit sheet).
- **Critic:** scores on a capped rubric.
- **Standards:** face, home location, rights, AI labels, health claims.
- **Fact-checker:** every on-screen number.

Fix the 3 worst issues and repeat. Done when every critic axis is 8 or more and nothing fails standards or fact checks. At most 3 rounds before you escalate to Samir. Log each round in `review.md`.

### 9. Package → `publish.md` → **Checkpoint 3**
Social editor role. Per platform:
- **Instagram:** caption ≤2,200 chars, hashtags, cover frame.
- **TikTok:** caption, hashtags.
- **YouTube Shorts:** title ≤100 chars, description.

Also include:
- the AI-label setting per platform: on if any realistic AI media is used; normally off
- the posting checklist
- **next week's shot list**: 3–5 shots to film on runs this week, for future angles

Append this week's entry to `journey/story-log.md`, leaving the links and stats blank for him to fill in.

**Checkpoint 3:** final cut and captions. He posts by hand. Never post, upload or schedule.

## Status

`/marathon-week status <id>` lists `weeks/<id>/` files in flow order with ✓/✗, the open checkpoint, and the next action. Read-only.
