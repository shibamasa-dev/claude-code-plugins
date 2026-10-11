# Self-review (at the storyboard stage and after the final render)

The agent **actually looks at** the frames it produced **with Read** and scores them. Do not score without looking.

## When

| Timing | What to look at | After fixing |
|---|---|---|
| After the storyboard, before showing a human | The cuts in `out/storyboard/cutsheet.html` (first frame / last frame in `<aspect>/cuts/`), contact.png / strip.png / phone.png / seam.png and the representative frames in `out/storyboard/<aspect>/`, and if there is sound, spectrogram.png and audio.json in `out/storyboard/audio/` | Rebuild the storyboard at the same stage |
| After the final render | poster.png / contact.png in `out/deliver/<aspect>/` | Fixing means changing the source, so **rebuild from the storyboard and get the human's OK again** (approval is tied to the source hash) |

## 9 items (each 1–10)

| Item | What to look at | Guide for 8 or higher |
|---|---|---|
| Hook (first 2 seconds) | First 4 frames of contact | Something moves within 0.5 seconds, and by 2 seconds it is clear what the video is about |
| Readability on a phone | phone.png | All text is readable even at 390px width. No thin or tiny type |
| Motion quality | strip.png (12 frames around the fastest motion) | Blur follows the direction of motion. No jumps between frames. Text does not overshoot |
| Visual change | All of contact, storyboard warnings | Something new happens every 2–4 seconds (0 "no noticeable change" warnings) |
| Composition | Representative frames | Whitespace is deliberate. Text does not cut into the safe area (6% from the edges). Re-laid out properly per aspect |
| Brand accuracy | Representative frames, poster | Uses only brand.json's colors, typefaces and logo. The logo is not distorted |
| Audio sync | beats.json and contact, `audio/spectrogram.png`, `audio/audio.json` | State changes sit on beats and the hero's entrance on bar starts (0 audio warnings). With BGM, the music's peaks land on the green lines (peaks) and BGM dips at sound effect moments. In per-band RMS, low does not exceed lowmid |
| Genericness | All of contact, first frame / last frame on the cut sheet | Not drifting toward a "plausible average". Not the black background + heavy type + particles + glitch combo, or any default look seen elsewhere. At least one shot exists for a reason specific to this video |
| Pacing contrast | contact and the cut sheet, top to bottom | Not everything at the same intensity. There are 1–2 clear hero (key) cuts, and also cuts that ease off (quiet, short, lots of whitespace). In visually loud cuts, overlays such as text and labels are kept quiet |

## Steps

1. Score the 9 items.
2. List **the worst 3** with timestamps (e.g. `4.20s: right card's text gets crushed on phone (readability 5)`).
3. Fix them. To check, re-render only those seconds:
   `node <skill>/scripts/render.mjs stills <project> --from 4.0 --to 4.5` (lined up in `out/stills/<aspect>/sheet.png`)
4. Show old and new scores side by side (e.g. `readability 5 → 8`).
5. Repeat 2–4 until every item is 8 or higher. Items that do not improve after 3 rounds go to the human as-is for a decision (with the score and reasons).

How to fix low genericness or pacing contrast:

- **Remove rather than add**. Delete textures, cuts and overlays that look unfinished (particles that do nothing, meaningless glitches, tiny text no one is meant to read) before trying to fix them
- Pick the hero cut and take everything else down a notch (less motion, fewer colors, fewer overlays)
- Do not fall back on black background + heavy type. Get tactility from brand.json's colors and live-action textures (`authoring.md`, "13. Layering live-action textures")

How to present it to the human:

```
Cut sheet: out/storyboard/cutsheet.html (v2)
Storyboard: out/storyboard/storyboard.md
Self-review: hook 8 / readability 8 / motion 9 / change 8 / composition 8 / brand 9 / audio 8 / genericness 8 / pacing contrast 8
Fixed 3: 4.20s text crushed (5→8), …
If OK, I'll do the final render.
```
