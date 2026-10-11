# Upload Plan: launch batch (15 videos) → Instagram, YouTube Shorts, TikTok

> Historical: launch set (September–October 2026). Its compositions (`src/scenes`, `src/theme.ts`), launch music and `out/*.mp4` renders were deleted in rebuild Phase 1 (8 October 2026); the pre-rebuild backup tarball holds them. Current layout: `AGENTS.md`.

Drafted 2026-10-01. Companion to `MARKETING_VIDEO_PLAN.md`. Files are in `out/`, all 1080×1920, 30 fps, H.264, under 20 MB, with burned-in captions and original audio.

**The goal of every post is one tap through and one finished puzzle.** None of the three platforms makes caption links clickable for a normal account, so the click has to come from the **profile link**, an **Instagram Story link sticker** or an **Instagram DM**. Every caption below ends by pointing to one of those.

---

## 1. Platform link facts (checked 2026-10-01)

| | Clickable from the post? | What *is* clickable | Plan |
|---|---|---|---|
| **Instagram Reels** | No. Caption URLs are plain text (clickable Reel links need Meta Verified business Plus+) | Bio (up to 5 links), Story link sticker, DMs | Bio links + a Story with a link sticker after each Reel + "comment PLAY" auto-DM |
| **YouTube Shorts** | No. Description and comment URLs have been plain text since Aug 2023 | Channel links (up to 14, first one shows in the header), **Related Video** link on each Short (YouTube videos only) | URL as the first description line (copyable), channel links, Related Video → Hero |
| **TikTok** | No | One bio link. Personal accounts may need 1,000 followers; **Business accounts have no minimum** | Business account, rotate the bio link to match the day's game |

Our audio is original, so a TikTok Business account loses nothing (it only restricts the commercial music library).

---

## 2. One-time setup (do before Day 1)

### 2.1 Tracking links

`acquisition.ts` keeps `utm_source/medium/campaign/content`, sanitising to `[a-zA-Z0-9._-]`, 64 chars max. All values below survive it unchanged (checked against `safeValue`).

Naming: `utm_source` = `instagram | youtube | tiktok`, `utm_medium` = where the click happened (`bio | story | dm | channel`), `utm_campaign` = the video (`launch_hero`, `teaser_scalar`, `playalong_ep03`, `asmr_globe`, …).

**Profile links (stable):**

| Platform | Label | URL |
|---|---|---|
| Instagram bio link 1 | Today's 4 puzzles | `https://scalargame.com/?utm_source=instagram&utm_medium=bio&utm_campaign=launch` |
| Instagram bio link 2 | Scalar: name the country | `https://scalargame.com/scalar?utm_source=instagram&utm_medium=bio&utm_campaign=launch` |
| Instagram bio link 3 | Continuum: rank the world | `https://scalargame.com/continuum?utm_source=instagram&utm_medium=bio&utm_campaign=launch` |
| Instagram bio link 4 | Whenabouts: place it in time | `https://scalargame.com/whenabouts?utm_source=instagram&utm_medium=bio&utm_campaign=launch` |
| Instagram bio link 5 | Tectonic: build the world | `https://scalargame.com/tectonic?utm_source=instagram&utm_medium=bio&utm_campaign=launch` |
| YouTube channel link 1 (shows in header) | Play today's puzzles | `https://scalargame.com/?utm_source=youtube&utm_medium=channel&utm_campaign=launch` |
| YouTube channel links 2–5 | Scalar / Continuum / Whenabouts / Tectonic | same pattern, `utm_source=youtube&utm_medium=channel` |
| TikTok bio link (rotates, see §4) | — | `https://scalargame.com/?utm_source=tiktok&utm_medium=bio&utm_campaign=launch` |

**Per-video links (Story stickers and DMs only):** `https://scalargame.com<deep link>?utm_source=instagram&utm_medium=story|dm&utm_campaign=<campaign>`. Deep link and campaign for each video are in §5.

**Known gap:** the end cards show `scalargame.com/scalar` etc. People who type that arrive as *direct* with no UTM. Watch direct entries on `/scalar`, `/continuum`, `/whenabouts`, `/tectonic` on posting days as a proxy.

### 2.2 Pre-launch tests (30 minutes, catches the expensive mistakes)

1. **Attribution:** open the Instagram bio link 1 from inside the Instagram app (in-app browser), play one puzzle, and confirm in PostHog that the session has `first_touch_source = instagram`, `first_touch_medium = bio`. Repeat once inside the TikTok in-app browser. In-app webviews can block storage, so also confirm the game loads and saves progress there.
2. **Music claims:** upload `Hero.mp4` to YouTube as **Private** and wait for the copyright check (Checks step in the upload flow, or Studio → Content → Restrictions). AI-music tools sometimes register tracks with Content ID. If it's clean, schedule it. If it's claimed, stop and check the tool's licence before posting anything.
3. **Licence record:** `public/music/TRACKS.md` still has `?` for tool and attribution. Fill it in. If the tool requires attribution, add a "Music: …" line to every description.

### 2.3 Account settings

**Instagram** (posting from your personal account)
- Switch to a **Creator** account (Settings → Account type and tools). It's free and stays personal, and you need it for Insights (reach, 3-second views, link taps) and for comment-to-DM automation.
- Settings → Data usage and media quality → **Upload at highest quality: on.**
- Bio: keep your bio, add one line: `Making scalargame.com: 4 daily puzzles for thinkers ↓`, then the 5 links above.
- Optional but the best per-video tracker on IG: **comment-to-DM** (ManyChat's free tier or similar, uses the official Instagram API). Keyword `PLAY` → DM with that video's `utm_medium=dm` link. If you skip this, delete the "Comment PLAY" line from the captions.

**YouTube**
- Channel name **Scalargame**, handle `@scalargame` (or closest available), profile image = the Venn logo.
- Channel description: `Four daily puzzles for thinkers. Name the country, rank the world, place it in time, build the globe. Free, no sign-up. Play at scalargame.com`
- Add the 5 channel links above (link 1 shows under the channel name).
- Create 3 playlists: **Play Along** (ep01–ep08), **Game Teasers** (4 teasers), **Tectonic ASMR** (2). Shorts in playlists get a "watch next" path.

**TikTok**
- Switch to a **Business account** (Settings → Account → Switch to Business account, category "Games" or "Education"). That gets the website link without a follower minimum.
- Bio (80 chars): `4 daily puzzles for thinkers. Free, no sign-up ↓`
- In the upload screen, turn on **HD upload** (More options → Upload quality → HD) and keep data saver off.

---

## 3. Settings for every upload

Upload the **file from `out/`** to every platform. Never re-upload a TikTok-downloaded copy to Instagram or YouTube (the watermark gets deprioritised). Don't add platform music: the soundtrack is part of the timing.

### Instagram Reel
| Setting | Value |
|---|---|
| Cover | Pick the frame listed per video in §5. Then **Edit profile image** so the key text sits inside the 4:5 grid crop |
| Caption | From §5. **Max 5 hashtags** (Instagram's limit) |
| Topics | Up to 3: Geography / Trivia / Puzzles / History (per video) |
| Audio name | Rename original audio to `Scalargame – <video title>` (tap audio → Rename) |
| Tag people / Location / Collab | None |
| Advanced → Alt text | One sentence describing the video (from §5's "Alt" line) |
| Advanced → Allow remixing | **On** (remixes of play-alongs carry the link-in-bio) |
| Advanced → Hide like counts | Off |
| Share to Facebook | Your call; free extra reach if you use FB |
| Trial reel | Off for launch batch. Use it in batch two to A/B hooks with non-followers |
| After posting | Within 10 min: **Story** with the Reel + a **link sticker** to the per-video `utm_medium=story` link. Sticker text: `Play today's` + game name. (If the link sticker isn't in your sticker tray, skip this and rely on bio + DM.) |
| Pin to grid | Pin **Hero** on Day 1. After week 2 pin the top 2 performers next to it |

### YouTube Short
| Setting | Value |
|---|---|
| Title | From §5 (under 70 chars, no spoilers) |
| Description | From §5. URL on line 1 so it shows in the collapsed view |
| Audience | **No, it's not made for kids.** (Made-for-kids disables comments, which kills the play-along hook) |
| Altered or synthetic content | **No** (applies to realistic AI depictions of people, places or events; these are motion graphics and real screen captures) |
| Related video | **Hero** for every Short except Hero itself; Hero → TeaserScalar |
| Playlist | Per §2.3 |
| Tags | `scalargame, geography quiz, daily puzzle, trivia` + per-game words (low impact, but free) |
| Category | Gaming |
| Comments | On, "hold potentially inappropriate comments" |
| Remixing | Allow video and audio remixing |
| Visibility | Schedule. Publish at your chosen slot (§4) |
| Pinned comment | From §5 |

### TikTok
| Setting | Value |
|---|---|
| Caption | From §5 (same text as Instagram; TikTok search reads it, so the keywords matter) |
| Cover | Frame listed in §5 |
| Who can watch | Everyone |
| Allow comments | On |
| Allow Duet / Stitch | **On** (stitched play-along answers are free reach) |
| Content disclosure → Your brand | **On.** You're promoting your own product; this is TikTok's compliant setting (adds a "Promotional content" label) |
| AI-generated content | Off (same reasoning as YouTube) |
| Bio link | Rotate per §4 *before* posting |
| Pinned comment | From §5 |
| Pin to profile | Pin Hero on Day 1 |

### First hour after every post (all platforms)
- Reply to every comment in the first 60 minutes. On play-alongs reply "got it?" style, never with the answer before the video does.
- On TikTok, answer the best comment with a **Reply with video** using the next play-along. That's a free extra post.
- Don't delete and re-post an underperformer. Leave it; note it in the review.

---

## 4. Schedule

One post a day, same slot on all three platforms, posted within the same hour. Default slot **6–8 pm in your timezone**. After week 1, move it to the peak hour shown in Instagram Insights (Audience → Most active times).

| Day | Date | Video | TikTok bio link that day | Pin |
|---|---|---|---|---|
| 1 | Mon 5 Oct | **Hero** | `/` · `utm_campaign=launch_hero` | Pin everywhere |
| 2 | Tue 6 Oct | TeaserScalar | `/scalar` · `teaser_scalar` | |
| 3 | Wed 7 Oct | TeaserContinuum | `/continuum` · `teaser_continuum` | |
| 4 | Thu 8 Oct | TeaserWhenabouts | `/whenabouts` · `teaser_whenabouts` | |
| 5 | Fri 9 Oct | TeaserTectonic | `/tectonic` · `teaser_tectonic` | |
| 6 | Sat 10 Oct | AsmrGlobe | `/tectonic` · `asmr_globe` | |
| 7 | Sun 11 Oct | PlayAlong ep01 (Guess the Country) | `/scalar` · `playalong_ep01` | |
| 8 | Tue 13 Oct | PlayAlong ep03 (Higher or Lower) | `/continuum` · `playalong_ep03` | |
| 9 | Thu 15 Oct | PlayAlong ep05 (What Year) | `/whenabouts` · `playalong_ep05` | |
| 10 | Sat 17 Oct | AsmrRegions | `/tectonic/regions` · `asmr_regions` | |
| 11 | Sun 18 Oct | PlayAlong ep07 (Where Does It Go) | `/tectonic` · `playalong_ep07` | |
| 12 | Tue 20 Oct | PlayAlong ep02 | `/scalar` · `playalong_ep02` | |
| 13 | Thu 22 Oct | PlayAlong ep04 | `/continuum` · `playalong_ep04` | |
| 14 | Sat 24 Oct | PlayAlong ep06 | `/whenabouts` · `playalong_ep06` | |
| 15 | Sun 25 Oct | PlayAlong ep08 | `/tectonic` · `playalong_ep08` | |
| — | Mon 26 Oct | **Review** (§6), plan batch two | Back to `/` · `launch` | |

TikTok bio links use `utm_source=tiktok&utm_medium=bio`, e.g. `https://scalargame.com/scalar?utm_source=tiktok&utm_medium=bio&utm_campaign=teaser_scalar`. Rotating it gives TikTok rough per-video attribution with only one link. On Instagram, keep the 5 bio links stable and rely on the Story sticker for per-video links.

The play-alongs interleave the four games so no game repeats on consecutive play-along days.

---

## 5. Per-video copy

Conventions:
- **Caption** = Instagram and TikTok (identical; paste as is). If you skip comment-to-DM, delete the "Comment PLAY" line.
- **YT title / YT description / Pinned** = YouTube (pinned comment works on TikTok and Instagram too).
- **Story link** = Instagram Story sticker URL. DM link = same with `utm_medium=dm`.
- **No spoilers** in any caption, title, cover or hashtag of the hero riddle and play-alongs. The video reveals; the text never does.

---

### 1. Hero — "Four ways to know the world" · `out/Hero.mp4` · 38 s
- **Deep link:** `/` · **campaign:** `launch_hero`
- **Cover:** ~0:03, the riddle card with all three clue stickers (not the answer stamp at 0:31)
- **Alt:** Animated trailer for Scalargame showing four daily puzzle games: naming a country from clues, ranking countries, guessing a year, and building a 3D globe.
- **Topics (IG):** Geography, Trivia, Puzzles

**Caption**
```
Landlocked. Drives on the left. 8 neighbours. Which country?
Answer at the end.

Scalargame is 4 daily puzzles: name the country, rank the world, place it in time, build the globe.
Free. No sign-up. Play one, it takes 2 minutes.

Link in bio · Comment PLAY and I'll DM it to you
#geography #dailypuzzle #trivia #geographyquiz #scalargame
```

**YT title:** `Landlocked, drives on the left, 8 neighbours. Which country?`

**YT description**
```
Play free: scalargame.com

4 daily puzzles. Free, no sign-up.
Scalar: name the country from clues
Continuum: rank the world
Whenabouts: place it in time
Tectonic: build the globe

Photo: Great Wall of China at Jinshanling by Severin.stalder, CC BY-SA 3.0, via Wikimedia Commons. Map data: Natural Earth.
Built by Samir.

#geography #trivia #dailypuzzle
```

**Pinned:** `Did you get it before the reveal? Today's 4 puzzles are live at scalargame.com`

---

### 2. TeaserScalar · `out/TeaserScalar.mp4` · 14 s
- **Deep link:** `/scalar` · **campaign:** `teaser_scalar`
- **Cover:** ~0:01, "Name the country."
- **Alt:** A geography puzzle where each guessed country shows green, orange or arrow clues until the answer is found.
- **Topics:** Geography, Puzzles

**Caption**
```
Name the country. Every guess tells you how close you are.
Green = exact. Orange = hot. Arrows point to the answer.

A new country every day. Free, no sign-up.
Link in bio · Comment PLAY for the link
#geography #geographyquiz #dailypuzzle #quiz #scalargame
```

**YT title:** `Name the country. Every guess gets warmer.`

**YT description**
```
Play today's puzzle: scalargame.com/scalar

A new country every day. Each guess shows how close you are on area, population, borders, location and more. Free, no sign-up.

#geography #geographyquiz #dailypuzzle
```

**Pinned:** `How many guesses would you need? Today's country: scalargame.com/scalar`

---

### 3. TeaserContinuum · `out/TeaserContinuum.mp4` · 14 s
- **Deep link:** `/continuum` · **campaign:** `teaser_continuum`
- **Cover:** ~0:01, "Rank these by population."
- **Alt:** Country cards being dragged into a ranking by population, with a wrong placement costing a life.
- **Topics:** Geography, Trivia

**Caption**
```
Rank these by population. No googling.
Wrong slot costs a life. 3 lives. How far can you go?

New ranking every day. Free, no sign-up.
Link in bio · Comment PLAY for the link
#geography #trivia #dailypuzzle #population #scalargame
```

**YT title:** `Rank these countries by population. No googling.`

**YT description**
```
Play today's ranking: scalargame.com/continuum

Drag each country into the right slot. A wrong slot costs a life, and you get 3. New metric every day. Free, no sign-up.

#geography #trivia #dailypuzzle
```

**Pinned:** `What's your best streak without losing a life? scalargame.com/continuum`

---

### 4. TeaserWhenabouts · `out/TeaserWhenabouts.mp4` · 14 s
- **Deep link:** `/whenabouts` · **campaign:** `teaser_whenabouts`
- **Cover:** ~0:01, "What year…" with the event photo
- **Alt:** A history puzzle showing a photo of the Eiffel Tower and a year scrubber being dragged to guess when it opened.
- **Topics:** History, Trivia

**Caption**
```
What year was this?
Drag the scrubber, lock it in. The closer you are, the more points.

Five events a day. Free, no sign-up.
Link in bio · Comment PLAY for the link
#history #historyquiz #trivia #dailypuzzle #scalargame
```

**YT title:** `What year did this happen? A daily history puzzle`

**YT description**
```
Play today's 5 events: scalargame.com/whenabouts

Guess the year of five real events. Closer guesses score more. Free, no sign-up.

Photo: Eiffel Tower by Benh LIEU SONG, public domain, via Wikimedia Commons.

#history #historyquiz #trivia
```

**Pinned:** `Closest guess wins. Today's 5 events: scalargame.com/whenabouts`

---

### 5. TeaserTectonic · `out/TeaserTectonic.mp4` · 14 s
- **Deep link:** `/tectonic` · **campaign:** `teaser_tectonic`
- **Cover:** ~0:05, half-built globe on dark
- **Alt:** Countries snapping one by one onto a 3D globe until all 194 are placed.
- **Topics:** Geography, Puzzles

**Caption**
```
Build the world. 194 countries, one at a time.
Then 200 more levels in Regions.

Free. No sign-up.
Link in bio · Comment PLAY for the link
#geography #maps #satisfying #puzzlegame #scalargame
```

**YT title:** `Build the world, one country at a time`

**YT description**
```
Play: scalargame.com/tectonic

Place all 194 countries on a 3D globe. 200 more levels in Regions. Free, no sign-up.

Map data: Natural Earth.

#geography #maps #satisfying
```

**Pinned:** `Which country would you place first? scalargame.com/tectonic`

---

### 6. AsmrGlobe — "Build the world" · `out/AsmrGlobe.mp4` · 25 s, loops
- **Deep link:** `/tectonic` · **campaign:** `asmr_globe`
- **Cover:** ~0:12, globe mostly filled
- **Alt:** A 3D globe filling in country by country, each with a soft note, until 194 countries are placed.
- **Topics:** Geography, ASMR

**Caption**
```
194 countries. One note each.
Sound on.

Build it yourself: link in bio
#asmr #satisfying #geography #maps #scalargame
```

**YT title:** `194 countries, one note each (sound on)`

**YT description**
```
Build the globe yourself: scalargame.com/tectonic

Every country snaps in with its own note. Free, no sign-up.

Map data: Natural Earth.

#asmr #satisfying #geography
```

**Pinned:** `Sound on. Build it yourself: scalargame.com/tectonic`

---

### 7. AsmrRegions — "Blast & reassemble" · `out/AsmrRegions.mp4` · 20 s, loops
- **Deep link:** `/tectonic/regions` · **campaign:** `asmr_regions`
- **Cover:** ~0:01, assembled South America
- **Alt:** A map of South America blasts apart and the countries snap back into place one by one.
- **Topics:** Geography, ASMR

**Caption**
```
South America, taken apart and put back together.
Sound on. 200 levels.

Try one: link in bio
#asmr #satisfying #geography #southamerica #scalargame
```

**YT title:** `South America, blasted apart and rebuilt (sound on)`

**YT description**
```
Play Regions: scalargame.com/tectonic/regions

200 levels. Put every region back together. Free, no sign-up.

Map data: Natural Earth.

#asmr #satisfying #geography
```

**Pinned:** `Could you rebuild it without the outlines? scalargame.com/tectonic/regions`

---

### Play-along series (8 × 15 s)

Shared for all eight:
- **Cover:** ~0:01.5, the question with its clue stickers, **never** the reveal (0:10+)
- The on-screen CTA says "Today's set is live · Link in bio", so captions repeat it.
- **Pinned comment (all eight):** `Answer drops at 0:10. What did you guess?` Post a second comment with the game link: `Today's real puzzle: scalargame.com/<game>`.
- Hashtags rotate per game below.

#### ep01 — Guess the Country · `out/PlayAlong-ep01.mp4`
- **Deep link:** `/scalar` · **campaign:** `playalong_ep01`
- **Alt:** Three clues appear (Americas, landlocked, 5 neighbours), a timer counts down, then the answer is revealed.

**Caption**
```
Pause & guess. Americas. Landlocked. 5 neighbours.
Comment your answer before the reveal. No googling.

Today's set is live: link in bio
#geographyquiz #geography #trivia #quiz #scalargame
```
**YT title:** `Americas, landlocked, 5 neighbours. Which country?`
**YT description**
```
Play today's country: scalargame.com/scalar

Three real clues from Scalar. Guess before the reveal at 0:10.

#geographyquiz #geography #trivia
```

#### ep02 — Guess the Country · `out/PlayAlong-ep02.mp4`
- **Deep link:** `/scalar` · **campaign:** `playalong_ep02`
- **Alt:** Three clues appear (Asia, landlocked, federal republic), a timer counts down, then the answer is revealed.

**Caption**
```
Pause & guess. Asia. Landlocked. Federal republic.
Comment your answer before the reveal. No googling.

Today's set is live: link in bio
#geographyquiz #geography #trivia #quiz #scalargame
```
**YT title:** `Asia, landlocked, federal republic. Which country?`
**YT description**
```
Play today's country: scalargame.com/scalar

Three real clues from Scalar. Guess before the reveal at 0:10.

#geographyquiz #geography #trivia
```

#### ep03 — Higher or Lower? · `out/PlayAlong-ep03.mp4`
- **Deep link:** `/continuum` · **campaign:** `playalong_ep03`
- **Alt:** Japan and Mexico side by side with the question which has more people, then the populations are revealed.

**Caption**
```
Japan or Mexico: which has more people?
It's closer than you think. Comment before the reveal.

Today's ranking is live: link in bio
#geography #trivia #population #quiz #scalargame
```
**YT title:** `Japan or Mexico: which has more people?`
**YT description**
```
Play today's ranking: scalargame.com/continuum

Population figures from Continuum's data. Guess before the reveal at 0:10.

#geography #trivia #population
```

#### ep04 — Higher or Lower? · `out/PlayAlong-ep04.mp4`
- **Deep link:** `/continuum` · **campaign:** `playalong_ep04`
- **Alt:** Kazakhstan and Argentina side by side with the question which is bigger, then their areas are revealed.

**Caption**
```
Kazakhstan or Argentina: which is bigger?
They're within 2% of each other. Comment before the reveal.

Today's ranking is live: link in bio
#geography #trivia #maps #quiz #scalargame
```
**YT title:** `Kazakhstan or Argentina: which is bigger?`
**YT description**
```
Play today's ranking: scalargame.com/continuum

Land area from Continuum's data. Guess before the reveal at 0:10.

#geography #trivia #maps
```

#### ep05 — What Year? · `out/PlayAlong-ep05.mp4`
- **Deep link:** `/whenabouts` · **campaign:** `playalong_ep05`
- **Alt:** A photo of the Colosseum with the question what year it was inaugurated, then the year is revealed.

**Caption**
```
What year was the Colosseum inaugurated?
Closest guess in the comments wins. No googling.

Today's 5 events are live: link in bio
#history #historyquiz #ancientrome #trivia #scalargame
```
**YT title:** `What year was the Colosseum inaugurated?`
**YT description**
```
Play today's 5 events: scalargame.com/whenabouts

A real event from a past Whenabouts puzzle. Guess before the reveal at 0:10.

Photo: Colosseo 2020 via Wikimedia Commons, CC BY-SA 4.0 (author: see commons.wikimedia.org/wiki/File:Colosseo_2020.jpg).

#history #historyquiz #ancientrome
```
**Credit required (CC BY-SA 4.0).** `image_credits.json` lists the author as "FeaturedPics", which looks like a Commons template rather than a person. Open the file page, copy the real author name into the credit line above (and into the Instagram/TikTok caption as `Photo: <author>, CC BY-SA 4.0, Wikimedia Commons`) before posting.

#### ep06 — What Year? · `out/PlayAlong-ep06.mp4`
- **Deep link:** `/whenabouts` · **campaign:** `playalong_ep06`
- **Alt:** The famous photo of the Wright brothers' first flight with the question what year it happened, then the date is revealed.

**Caption**
```
What year did the Wright brothers first fly?
Closest guess in the comments wins. No googling.

Today's 5 events are live: link in bio
#history #historyquiz #aviation #trivia #scalargame
```
**YT title:** `What year did the Wright brothers first fly?`
**YT description**
```
Play today's 5 events: scalargame.com/whenabouts

A real event from a past Whenabouts puzzle. Guess before the reveal at 0:10.

Photo: John T. Daniels, public domain, Library of Congress.

#history #historyquiz #aviation
```

#### ep07 — Where Does It Go? · `out/PlayAlong-ep07.mp4`
- **Deep link:** `/tectonic` · **campaign:** `playalong_ep07`
- **Alt:** A country is highlighted on a 3D globe in Asia with the question name the country, then the name is revealed.

**Caption**
```
Name the highlighted country.
Comment before the reveal. No googling.

Build the whole globe: link in bio
#geographyquiz #geography #maps #quiz #scalargame
```
**YT title:** `Can you name the highlighted country?`
**YT description**
```
Play Tectonic: scalargame.com/tectonic

Place all 194 countries on the globe. Guess before the reveal at 0:10.

Map data: Natural Earth.

#geographyquiz #geography #maps
```

#### ep08 — Where Does It Go? · `out/PlayAlong-ep08.mp4`
- **Deep link:** `/tectonic` · **campaign:** `playalong_ep08`
- **Alt:** A country is highlighted on a 3D globe in Southeast Asia with the question name the country, then the name is revealed.

**Caption**
```
Name the highlighted country. Harder than it looks.
Comment before the reveal. No googling.

Build the whole globe: link in bio
#geographyquiz #geography #maps #quiz #scalargame
```
**YT title:** `Name the highlighted country (harder than it looks)`
**YT description**
```
Play Tectonic: scalargame.com/tectonic

Place all 194 countries on the globe. Guess before the reveal at 0:10.

Map data: Natural Earth.

#geographyquiz #geography #maps
```

---

## 6. Measurement and review

### What to log after 48 hours (per video × platform)

Keep one sheet, one row per post:

| Column | Instagram | YouTube | TikTok |
|---|---|---|---|
| Views | Views | Views | Video views |
| Hook hold | 3-second view rate | **Viewed vs swiped away** | % watched past 2–3 s (retention graph) |
| Avg % watched | Avg watch time ÷ length | Avg % viewed | Avg watch time ÷ length |
| Loops / rewatch | Plays vs reach | % viewed > 100% | Full-video watch rate |
| Shares + saves | ✓ | Shares | ✓ |
| Comments | ✓ | ✓ | ✓ |
| Profile visits | ✓ | Channel views (Studio) | Profile views |
| Link clicks | **External link taps** + Story sticker taps | — | Bio link clicks (Business analytics) |

### Site side (PostHog)

- Sessions by `first_touch_source` × `first_touch_campaign`, and the funnel from the main plan: landing → game loaded → first meaningful action → terminal Daily result. Report counts, not just rates; the launch batch will be small.
- Direct-entry spikes on `/scalar`, `/continuum`, `/whenabouts`, `/tectonic` on each game's posting day (people typing the end-card URL).

### Review on Mon 26 Oct
1. Which **format** wins on link clicks per 1,000 views: hero, teaser, play-along or ASMR?
2. Which **game** converts best from click to finished puzzle?
3. Which **platform** sends finishers, not just views?
4. Set the first numeric targets from these baselines (the main plan says not to invent them before now).
5. Batch two = more of the winning format, new play-along episodes from `playalong.json` (data row only), and Trial Reels to A/B the top hook.

---

## 7. Final checklist per post

- [ ] Right file from `out/`, uploaded natively (not a re-download)
- [ ] Cover is the hook frame, not the reveal
- [ ] Caption has no spoiler, ≤ 5 hashtags, link line present
- [ ] Image credit line present (Hero, ep05 required; others courtesy)
- [ ] Natural Earth credit on every map video (Hero, TeaserTectonic, both ASMR, ep07, ep08)
- [ ] YouTube: not made for kids, Related Video → Hero, playlist set
- [ ] TikTok: bio link rotated to today's game, Your brand on, Duet/Stitch on
- [ ] Instagram: Story with link sticker posted, audio renamed
- [ ] First-hour comment replies done

Sources for §1 (checked 2026-10-01): Instagram caption links ([inro.social](https://www.inro.social/blog/meta-verified-clickable-links-instagram-reels-pricing), [Engadget](https://www.engadget.com/social-media/meta-is-testing-clickable-links-in-instagram-captions-for-verified-subscribers-184555406.html)); YouTube Shorts links ([link.boo](https://link.boo/guides/youtube-shorts-link-in-description), [unil.ink](https://unil.ink/blog/how-to-add-link-youtube-shorts)); TikTok bio links ([Outfy](https://www.outfy.com/blog/how-to-add-a-link-to-your-tiktok-bio/), [stan.store](https://stan.store/blog/tiktok-link-bio-requirements-2026-guide/)).
