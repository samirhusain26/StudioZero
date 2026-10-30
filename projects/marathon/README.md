# Marathon — project context

Samir's running channel: a plus-size (280 lb) runner going from a 5K (October 2026) to the **TCS New York City Marathon, Sunday 2028-11-05** (expected date; the first Sunday of November), earning the bib through the NYRR 9+1 program in 2027. One video a week, made with Claude every Sunday, posted by hand to Instagram, TikTok and YouTube Shorts. The project id `marathon` is a working name until the channel name is chosen.

Read `PLAN.md` first (decisions, roles, open items). This is a StudioZero project (moved in from its own folder on 2026-10-13) so every video asset, skill and tool lives in one repo, as a **manual project**: `studio.json` lists it under `manualProjects`, and `project.json` (summary, goal, accounts, what to bring, the prompt templates) feeds a card on the Pi's Studio › Overview with the prompts to paste into Claude Code. It has no batches, contract module, schedule, mix or publisher channels. After editing `project.json`, run `(cd publisher/ui && npm run build:static)` so the catalog the Pi serves matches. Paths in this file, `PLAN.md`, the `/marathon-week` skill and the `marathon-*` agents are relative to `projects/marathon/` unless they start with `.claude/`.

## Tree

```
README.md                this file
PLAN.md                  decisions, the team, the weekly flow, open items, next steps
brand/voice.md           the narrative and tone (who is talking, what we never say)
journey/timeline.md      fixed milestones (start, races, 9+1, NYC 2028)
journey/story-log.md     running continuity: each week's story, callbacks, open threads, what worked
weeks/<YYYY-Www>/        one folder per weekly video (ISO week, Mon–Sun; made on the Sunday); ignored by Git (StudioZero is public)
  intake/                ignored: the dump's raw files (Health export, clips, voice memos, screenshots)
  dump.md                the owner's weekly brain dump, verbatim
  facts.md / facts.json  the data analyst's week (facts.json holds route points)
  story.md slate.md script.md beats.md review.md publish.md   stage outputs (see the /marathon-week skill)
tools/health_export.py   Apple Health export → week facts (stdlib Python); tests in tools/tests/
.claude/skills/marathon-week/   (repo root) the weekly playbook (/marathon-week) and roles.md
.claude/agents/marathon-*      (repo root) independent roles: data-analyst, story-editor, fact-checker, critic, standards
```

## Commands

```bash
# from projects/marathon/
python3 tools/health_export.py <export.zip|export.xml> --from 2026-10-12 --to 2026-10-18 --out weeks/2026-W42
python3 -m unittest discover -s tools/tests -v
```

The renderer is not chosen yet. Remotion, as in StudioZero's motion engine, is the leading option; the brainstorm decides after the look is set.

## Hard rules

1. **Real or nothing.** Every number on screen comes from the owner's own data or his own words. AI never depicts him, his running, his body, his races or his results. Illustrative AI images or video only when clearly non-realistic, always labeled with each platform's AI label.
2. **No face.** Feet, legs, hands, back, shadow, POV, surroundings are fine. No identifiable shots of his face.
3. **Home stays private.** He is not anonymous (name and bibs are fine), but routes never show where he lives: drawn routes drop the first and last 0.2 mi, with no basemap; no house numbers or street signs near home.
4. **No training or medical advice, no weight-loss promises.** We show what he did and learned. Explainers cite sources (the fact-checker verifies them). Injury and health issues are told as story, never as advice.
5. **Body narrative with dignity.** The plus-size story is told in his words and on his terms (`brand/voice.md`). No fat jokes he did not make, no before/after framing he did not ask for.
6. **No paid generation** (image, video, voice models) without his explicit OK for that run, with a cost estimate. No new dependencies without asking.
7. **He posts.** Nothing is posted, scheduled or uploaded by an agent, and the StudioZero publisher never touches this project. Commits only when he asks.
8. **Public repo.** StudioZero is public (`docs/PUBLIC_SAFETY.md`). Week folders, Health exports, routes, clips and voice memos stay out of Git; `brand/`, `journey/`, `PLAN.md` and the tools are tracked.
