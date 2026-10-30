# Formats

Every episode is one format. Machine-readable spines and limits: `formats.json` (the episode checker enforces them). Rotation rules: never the same format two days running; at least 3 formats a week; vary the hook type.

Shared limits: 110–180 spoken words (45–75 s at about 2.5 words a second) · hook line ≤ 16 words, works muted · banner ≤ 5 words, states one fact the voice does not say · the last line calls back to the first frame so the loop feels intentional.

Lessons from the first cold reads (2026-10-14): banners are plain facts, not citations (one patent-number banner at most) · the hook banner names its subject · the viewer's question is asked out loud early and the payoff lands by about 25–30 s · the background and old-way beats get one short line each · jargon only when needed, defined in five words.

**Hook types** (vary them across the week): the surprising fact ("Your Roomba can't see the stairs.") · the question ("Why doesn't a Roomba fall down the stairs?") · the object ("This drawing is from 1958.") · the stakes ("This patent made a company billions.") · the contradiction ("The bladeless fan has blades.").

## How it works (`how-it-works`)
hook → problem → old-way → insight → mechanism → product → loop
- problem and old-way come only from the patent's background and cited references. **old-way is optional** (owner, 2026-10-14): skip it when the background has nothing relevant to the story.
- insight is one sentence, checked against claim 1: "Before, X caused Y. This patent does Z."
- mechanism is one worked example, not a list.
- product says only what the phrasing-ladder level allows, with the honest caveat.
- Example: Roomba cliff sensing (US 6,883,201).

## The patent behind the news (`behind-the-news`)
hook → news → question → patent → mechanism → impact → loop
- news: this week's story in one line, from a dated source; never a death, disaster or crime as the hook.
- question: the technical question the story raises.
- impact: why it matters now; no predictions stated as fact, no legal opinions.

## The weird drawing (`weird-drawing`)
hook → figure → reveal → mechanism → where → loop
- Opens on a redrawn patent figure (US, no copyright notice) with the question "what is this?".
- reveal names the patent; where says where people meet it, at the level the evidence allows.

## Expired, now everywhere (`expired-everywhere`)
hook → everyday → patent → mechanism → expiry → aftermath → loop
- expiry needs a dated status check in the ledger (USPTO record) or a reputable source for the expiry date.
- aftermath: what happened when it expired, sourced (copies, price drops, new products).

## Kitchen and home (`kitchen-home`)
hook → object → problem → patent → insight → loop
- An everyday object and the hidden problem it solves; the clever bit is the insight.

## Software you touch (`software-you-touch`)
hook → moment → invisible → method → impact → loop
- moment: something people see on a screen; invisible: what the software does that they cannot see; method: the patent's method in one worked example.
- "The idea <company> patented", not "how every device works today", unless the ledger reaches level 4.
