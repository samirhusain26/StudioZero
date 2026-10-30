# Explainers research (2026-10-13)

The evidence behind `SYSTEM.md`. Five inputs: the owner's motion-graphics master prompt (30 sources, 2026-10-12) and the 9-repo note, plus four research passes on 2026-10-13: AI video pipelines on GitHub, practitioner reports and platform policy, trend and patent data sources, and studio roles with multi-agent papers. Reddit could not be read directly (blocked); claims from it are second-hand and marked so. Star counts and vendor claims are as reported, not verified.

## 1. What the strongest systems have in common

| Finding | Evidence |
|---|---|
| **Plan before generating** is the biggest single quality lever | Code2Video ablation: removing the planner dropped aesthetics 79.0 → 38.1 and TeachQuiz 82.0 → 40.5 ([2510.01174](https://arxiv.org/html/2510.01174v1)); TheoremExplainAgent calls agentic planning essential ([2502.19400](https://arxiv.org/abs/2502.19400)) |
| **A critic that sees the render** helps; text-only review misses layout defects | Code2Video: removing the critic cost 21 points on TeachQuiz; a single wrapped glyph was caught only by viewing a still, not by lint ([note.com test](https://note.com/claudecode_lab/n/n29dd41f20da1?hl=en)) |
| **Constrained choice beats free-form** | Code2Video visual anchors: element layout 82.8 vs 48.8 free placement; PaperTalker's VLM picks among rule-made layouts ([2510.05096](https://arxiv.org/html/2510.05096v2)); json-render generates the LLM prompt from a Zod component catalog ([vercel-labs/json-render](https://github.com/vercel-labs/json-render)) |
| **Independent verification**, not self-review | LLMs struggle to self-correct without external feedback ([Huang et al.](https://arxiv.org/html/2310.01798v1)); judges prefer familiar output, including their own ([Wataoka et al.](https://arxiv.org/html/2410.21819v1)); answering verification questions apart from the draft reduces hallucination ([Chain-of-Verification](https://arxiv.org/pdf/2309.11495)); newsrooms separate checker from writer ([GIJN](https://gijn.org/resource/introduction-investigative-journalism-fact-checking/)) |
| **Role decomposition alone gives modest gains**; spend independence where errors correlate | MovieAgent +0.17 on a 5-point scale ([2503.07314](https://arxiv.org/html/2503.07314v1)); Anthropic's multi-agent research system: subagents need an explicit objective, output format, source guidance and boundaries; a CitationAgent attributes claims; early agents preferred SEO farms until source-quality rules were added ([engineering post](https://www.anthropic.com/engineering/multi-agent-research-system)) |
| **Narration first; timing from word onsets** | video_explainer runs TTS before the storyboard ([prajwal-y/video_explainer](https://github.com/prajwal-y/video_explainer)); papercut-explainer keys scene cues to word onsets so a re-voice does not break the build ([0xS4N4TG/papercut-explainer](https://github.com/0xS4N4TG/papercut-explainer)); a 12 s composition became 18.85 s once narration was added (note.com) |
| **One file per stage, resumable** | papercut-explainer, video-talkcraft, llm-video-maker, claude-code-video-toolkit (`project.json` + per-project CLAUDE.md) |
| **Cheap human gates at irreversible steps; capped review loops** | Studio sign-off order: script → style → storyboard → animatic → low-res cut ([Boords](https://boords.com/blog/the-seven-steps-of-animation-production)); papercut and talkcraft cap review at 2–3 rounds |

## 2. Repos and patterns worth borrowing

| Pattern | From | Licence note |
|---|---|---|
| Router skill + stage skills + narrow scene subagents; 9:16 Remotion reels; `facts.md` → `script.json` → `STORYBOARD.md` → `voice.json` → `plan.json` | [papercut-explainer](https://github.com/0xS4N4TG/papercut-explainer) | MIT |
| Banner states one fact the voice does not repeat | papercut-explainer | MIT |
| Recipe cards (intent, parameters, pitfalls, `.tsx`, preview); the shot copies the card's pitfalls; 12-column grid, type floor, non-overlapping boxes; build one sample shot first | [video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft), [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | talkcraft is **PolyForm Noncommercial**: patterns only, no code |
| Script lint before TTS (hook length, spoken numbers, line length); transcribe each take and compare to the script; Gemini TTS | [voice-film](https://github.com/artkruglov/voice-film) | MIT |
| Review receipt bound to the exact script hash; machine release gate; "the tool enforces process, not truth" | [claude-video-kit](https://github.com/runesleo/claude-video-kit) | MIT |
| One Zod-validated JSON in, loudnormed MP4 out; duration from props via `calculateMetadata`; never hotlink assets | [agentic-remotion-pipeline](https://github.com/ryanwi/agentic-remotion-pipeline) | MIT |
| Per-asset provenance manifest (role, source, licence); human polishes the script before TTS | [video-podcast-maker](https://github.com/Agents365-ai/video-podcast-maker) | MIT |
| Fact-check stage on a source document; timestamped feedback → re-render one scene | [paper2video](https://github.com/Lunamos/paper2video) | MIT |
| Proposal as the last cheap exit; gates enforced in code; append-only decision log | [OpenMontage](https://github.com/calesthio/OpenMontage) | AGPL: design only |
| House rules as code, contact-sheet critique with capped scores | [ai-motion-studio](https://github.com/qasimtalkin/ai-motion-studio), [app-promo-motion](https://github.com/patt-rick/app-promo-motion) | MIT |

No public repo turns patents into videos. Anthropic's "Claude Motion" (beta, 2026-10-08, Team/Enterprise) shows code-rendered explainers are now mainstream ([help page](https://support.claude.com/en/articles/17454997-get-started-with-claude-motion)).

**Remotion tooling we can use** (all same toolchain, already pinned at 4.0.529): `@remotion/install-whisper-cpp` (local, MIT; token-level timestamps merged to words; 16 kHz WAV in) and `@remotion/captions` (`Caption` type, `createTikTokStyleCaptions`) ([docs](https://www.remotion.dev/docs/install-whisper-cpp)); `@remotion/paths` (SVG path measure/draw-on); `@remotion/three` (3D; headless renders need `chromiumOptions: {gl: "angle"}`); `@remotion/lottie`; `@remotion/layout-utils` (text measuring/fitting). Remotion's official agent skills exist ([remotion.dev/docs/ai/skills](https://www.remotion.dev/docs/ai/skills)) but are coding conventions, not pipelines. Licence: free for individuals and companies up to 3 people; recheck before Remotion 5 ([LICENSE.md](https://raw.githubusercontent.com/remotion-dev/remotion/main/LICENSE.md)).

**Anti-patterns:** free-form LLM-written TSX per scene with no schema; even word spacing as shipped timing; generative video for factual beats; "a second model reviews" with no rubric; review receipts mistaken for truth.

## 3. Platform policy and audience

- **YouTube "inauthentic content"** (renamed from "repetitious" 2025-07-15): not monetizable if "mass-produced, generic, repetitive", including content that "looks like it's made with a template" or "AI-generated content made with generic or unoriginal templates" ([policy](https://support.google.com/youtube/answer/1311392)). July 2026 clarification targets template-based content ([TechCrunch](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/)). Reported enforcement is channel-level and pattern-based (secondary sources; detection method unpublished). **Templated sameness, not the AI voice, is the main risk.**
- **Disclosure:** YouTube requires it for realistic altered or synthetic content; animation, infographics and captions are exempt ([altered content](https://support.google.com/youtube/answer/14328491)). TikTok and Instagram label realistic AI people and scenes (secondary sources only). Abstract motion graphics with a neutral AI narrator sit outside the photoreal triggers (inference).
- **AI voice:** listener studies suggest quality matters less than perceived sameness and low value (contested, vendor-adjacent).
- **Hooks and length:** a concrete payoff in the first 2–3 s, a first frame readable on its own, 45–75 s within the range cited for education (no controlled data); last frame calls back to the first for replays. Benchmark against our own "viewed vs swiped away".
- **Failure reports:** overlapping text, off-screen objects and hallucinated facts are the most cited failures ([HN](https://news.ycombinator.com/item?id=42590290)); "the AI default look" is documented for web UI (Inter, purple-blue gradients, rounded card grids), and the fix is a written design system with references.
- **Daily posting** on a clone-heavy niche is linked to poor outcomes in creator anecdotes; variety and unique information per episode are the mitigation.

## 4. Roles in professional pipelines

Kurzgesagt: research → script (about a dozen drafts, experts check facts, a published sources sheet) → design → voice → animation → music ([process](https://kurzgesagt.org/youtube/)). Newsrooms: the reporter lists every fact and its source, an independent checker verifies each line, editors decide, legal or standards can hold publication ([PublicSource](https://www.publicsource.org/inside-our-newsroom-getting-things-right-for-you/)). Studios lock the animatic before production. Reviewers advise; the producer or editor decides; revisions are capped.

**Patent beat spine** (synthesis; no published framework exists): hook (0–3 s) → problem, from the patent's background (3–12) → the old way, from the patent's background and cited references (12–20) → the insight in one sentence, checked against the independent claim (20–30) → mechanism, one worked example (30–55) → the product link and impact, with a caveat (55–65) → loop-back (65–70). At about 2.5 words a second, 45–75 s is 110–190 words.

## 5. Trend and patent sources ($0, within terms)

| Source | Use | Terms |
|---|---|---|
| Google Trends "Trending now" RSS `trends.google.com/trending/rss?geo=US` | What is trending today (with news links) | No key; undocumented feed; Google ToS bars automation against robots rules: grey area, fetch once a day, cache |
| Hacker News Firebase API `hacker-news.firebaseio.com/v0/` | Tech and gadget signal | No key, "no rate limit" ([API](https://github.com/HackerNews/API)) |
| Wikimedia top pageviews `wikimedia.org/api/rest_v1/metrics/pageviews/top/...` | Corroboration | CC0 data; User-Agent with contact required ([policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html)) |
| ~~Google News RSS search~~ | — | **Not used:** the feed itself says it is "made available solely for the purpose of rendering Google News results within a personal feed reader for personal, non-commercial use" (checked 2026-10-14); robots.txt disallows it too |
| GDELT DOC API | News article lists for queries (replaces Google News) | Free for commercial use with a citation ([about](https://www.gdeltproject.org/about.html)); one request per 5 s, answers 429 when faster |
| Skip | Reddit (approval gate, non-commercial, AI clause), TikTok Creative Center (no API), Product Hunt (non-commercial API), Exploding Topics (paid API), YouTube Data API (30-day storage, poor fit) | |

| Patent source | Use | Notes |
|---|---|---|
| Google Patents patent pages `patents.google.com/patent/<n>/en` | Text, claims, figures, citations | robots.txt allows `/patent/`; **search URLs are disallowed**; status shown is "an assumption" |
| Google Patents Public Data (BigQuery) | Keyword/CPC/assignee search | First 1 TB/month free; refreshed about quarterly (later) |
| USPTO maintenance-fee lookup / Patent Center | Authoritative US status, dated | Required before saying "expired" or "active" on screen |
| EPO OPS | Families and legal events | Free 4 GB/week with registration (later) |
| USPTO PatentsView API | — | Shut down 2026-03-20 ([notice](https://www.uspto.gov/subscription-center/2026/patentsview-migrating-uspto-open-data-portal-march-20)) |
| Company patent-marking pages (35 U.S.C. 287) | Patent ↔ product link | e.g. [iRobot](https://www.irobot.com/en_US/patents.html); marking is a damages-notice rule, cite the page and date |

**Copyright of patents:** USPTO says patent text and drawings are "typically not subject to copyright restrictions" but a portion may be ([terms](https://www.uspto.gov/terms-use-uspto-websites)); 37 CFR 1.71(d)–(e) allows a notice at the start of the specification. Rule: check for a notice; redraw figures rather than reuse them; foreign patents only redrawn. iFixit content is CC BY-NC-SA and forbids AI training use: link and paraphrase, do not reuse its photos.

**Phrasing ladder** for patent claims: (1) record: "US Patent N, '<title>', granted to <assignee> on <date>" · (2) content: "the patent describes/claims …" (only claim language we read) · (3) marking: "<company> lists this patent for <product> on its marking page" (URL + date) · (4) "ships in <product>" only with a company statement, teardown or claim read; otherwise "a patent describing a similar approach". Never "this is how <product> works" without level 4; never "patent pending" as granted; "granted" is not "valid".
