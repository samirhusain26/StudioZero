# Track: Patents

One real patent per video. Any kind (owner, 2026-10-13): software, mechanical, kitchen, medical, consumer tech; an exploded view is one option, not a requirement. Rules: `../PLAN.md` §7. Research pass 2026-10-13 (bibliographic data from Google Patents; Google's status and expiry are estimates, so check USPTO Patent Center before saying "expired" or "active" on screen).

Evidence strength = how well a source other than the patent ties it to the shipping product.

## Backlog

| # | Patent | Product | Evidence | Exploded view | Notes |
|---|---|---|---|---|---|
| 1 | [US 7,311,526](https://patents.google.com/patent/US7311526B2/en) Magnetic connector for electronic device (Apple, filed 2005-09-26, granted 2007-12-25, expired) | MagSafe laptop power connector (2006) | Strong: Apple's [MacBook Pro release](https://www.apple.com/newsroom/2006/01/10Apple-Introduces-MacBook-Pro) calls it "patent-pending" and says it disconnects under strain; filing predates launch. No source prints the number next to the product | Plug housing, spring-loaded pins, magnets, socket keeper, strain relief | **Owner: not interested (2026-10-13).** |
| 2 | [US 6,883,201](https://patents.google.com/patent/US6883201B2/en) Autonomous floor-cleaning robot (iRobot, filed 2002-12-16, granted 2005-04-26, expired) | Roomba | Strong: [iRobot's patent page](https://www.irobot.com/en_US/patents.html) lists it for Roomba 600 through j series (checked 2026-10-13) | Chassis, main and side brushes, height-adjusting deck, dust bin, cliff sensors, wheels | **Owner: yes, first episode (2026-10-13).** Claim 1: cliff detector steers it away from a drop. Check the cliff sensor physics before scripting (infrared detail only from an i7 teardown blog) |
| 3 | [US 3,005,282](https://patents.google.com/patent/US3005282A/en) Toy building brick (Interlego, filed 1958-07-28, granted 1961-10-24, expired) | LEGO brick | Strong: [LEGO history page](https://www.lego.com/en-gb/history/articles/d-the-stud-and-tube-principle) (stud and tube, clutch power) | Shell, studs, tubes, section through two clamped bricks | LEGO protects its brand hard; little "reveal" |
| 4 | [US 8,232,973](https://patents.google.com/patent/US8232973B2/en) Word recommendations for text input (Apple, filed 2008-06-30, granted 2012-07-31, active) | iPhone keyboard: invisible, resizing key hit regions | Moderate: Kocienda's *Creative Selection* ([9to5Mac excerpt](https://9to5mac.com/2018/08/08/excerpt-iphone-software-keyboard-design/)) describes adjusting invisible touch targets; filed after the 2007 launch | Weak physically: glass, touch layer, display, plus an invisible hit map | Say "the idea Apple patented", not "how every iPhone works today" |
| 5 | [US 8,308,445](https://patents.google.com/patent/US8308445B2/en) Fan (Dyson, granted 2012-11-13, active); alternative [US 7,931,449](https://patents.google.com/patent/US7931449B2/en) | Dyson Air Multiplier bladeless fan | Moderate: Dyson product pages say "Patented Air Multiplier"; [court order](https://www.govinfo.gov/content/pkg/USCOURTS-azd-2_12-cv-00234/pdf/USCOURTS-azd-2_12-cv-00234-1.pdf) shows the design; no source matches a number to a model | Excellent: base, impeller, motor, hollow ring, slit, Coandă ramp | Most contested (1981 Japanese prior art, litigation); "15×" is marketing |
| 6 | [US 4,687,200](https://patents.google.com/patent/US4687200A/en) Multi-directional switch (Nintendo, granted 1987-08-18, expired) | The plus-shaped D-pad | Moderate: Nintendo's Emmy for the D-pad ([repost](https://www.nintendoworldreport.com/news/15068/nintendo-wins-an-emmy)); patent link via Wikipedia | Cross, rubber membrane, pads, PCB, pivot | Origin credit debated (1981 Microvision) |
| 7 | [US 5,961,804](https://patents.google.com/patent/US5961804A/en) Microencapsulated electrophoretic display (MIT, granted 1999-10-05, expired) | Kindle E Ink screen | Weak: technology lineage only ([Science Friday](https://www.sciencefriday.com/articles/how-electronic-ink-was-invented/), [Paperwhite optics paper](https://arxiv.org/pdf/1605.05174)) | Excellent: frontlight, electrode, capsule layer, backplane | Find an E Ink Corp patent with a clearer Kindle link first |
| 8 | [US 3,691,140](https://patents.google.com/patent/US3691140A/en) (Silver, 1972) and [US 5,194,299](https://patents.google.com/patent/US5194299A/en) (3M/Fry, 1993) | Post-it Notes | Moderate: [Inventors Hall of Fame](https://invent.org/inductees/spencer-silver) | Weak: paper, adhesive islands | Which patent covers today's note is unclear; the "accident" story is a myth |

Checked, not used yet: Dyson dual cyclone [US 4,593,429](https://patents.google.com/patent/US4593429A/en) (no source ties the number to a model; a good second Dyson backup), Gorilla Glass [US 7,666,511](https://patents.google.com/patent/US7666511B2/en) (no number-to-generation link; thin visual), Face ID dot projector [US 8,150,142](https://patents.google.com/patent/US8150142B2/en) (link to Face ID is rumour-grade), Nespresso (no patent confirmed).

## From the 2026-10-e00 scout (2026-10-14)

Opened on Google Patents by the scout; claims, status and product links still need the researcher. Full notes in that batch's `review/slate.md` (local).

| id | Patent | Format | Hook idea | Evidence | Notes |
|---|---|---|---|---|---|
| qr-finder | [US 5,726,435](https://patents.google.com/patent/US5726435A/en) NipponDenso/Toyota CRDL (Denso Wave), 1998 | expired-everywhere | the three corner squares read the same ratio at any angle | 3: [Denso Wave patent page](https://www.qrcode.com/en/patent.html) | expiry needs a dated USPTO check |
| first-down-line | [US 6,141,060](https://patents.google.com/patent/US6141060A/en) Fox Sports Productions, 2000 | software-you-touch | the yellow line isn't on the field | 4 for the 1998 debut ([ETHW](https://ethw.org/The_Making_of_Football%27s_Yellow_First-and-Ten_Line)) | NFL season; origin credit debated |
| pull-to-refresh | [US 8,448,084](https://patents.google.com/patent/US8448084B2/en) Twitter (Loren Brichter), 2013 | software-you-touch | a hidden trigger above the list | 2 + press (Innovator's Patent Agreement) | "the idea Twitter patented" |
| super-soaker | [US 4,591,071](https://patents.google.com/patent/US4591071A/en) Lonnie G. Johnson, 1986 | weird-drawing | the first patent's water gun made noises | USPTO's [Lonnie Johnson page](https://www.uspto.gov/kids/lonnie-johnson) | sold toy follows US 5,074,437; summer |
| foxtrax-puck | [US 5,912,700](https://patents.google.com/patent/US5912700A/en) Fox Sports Productions, 1999 | weird-drawing | a puck blinking invisible light | 4, historical (1996–98) | NHL season; pair with first-down-line |
| snow-gun | [US 2,676,471](https://patents.google.com/patent/US2676471A/en) TEY Manufacturing, 1954 | behind-the-news / expired-everywhere | snow only between 6 and 32 °F | 2 + history | ski season; contested origin |
| transformer-patent | [US 10,452,978](https://patents.google.com/patent/US10452978B2/en) Google, 2019 | weird-drawing | the "T" in GPT is a Google patent | 2 | encoder-decoder scope gap; abstract visual |
| tremor-anc | [US 11,701,293](https://patents.google.com/patent/US11701293B2/en) Encora, 2023 | how-it-works | noise-cancelling math for a shaking hand | 2 | medical wording care |
| force-cancelling | [US 10,631,096](https://patents.google.com/patent/US10631096B1/en) Apple, 2020 | behind-the-news | two parts built to fight each other | 1–2 | weak product link |

## In production

| Batch | id | Patent | Format | Stage |
|---|---|---|---|---|
| 2026-10-e00 (pilot) | roomba-cliff | US 6,883,201 (+ companion US 6,594,844) | how-it-works | script locked 2026-10-14 |
| 2026-10-e00 (pilot) | taction-haptics | US 10,659,885 (+ US 10,820,117) | behind-the-news | script locked 2026-10-14; live litigation: re-check the docket before C4 and posting |

## Done

(none posted yet)
