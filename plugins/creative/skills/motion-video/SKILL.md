---
name: motion-video
description: Renders motion-graphics videos (intro videos, product demos, vertical short-form for social, loops) that feature product images, screenshots, logos and live-action clips, by drawing each frame in code and exporting mp4. The agent writes an HTML/Canvas seek(t) renderer, headless Chrome turns it into a 60fps image sequence, and ffmpeg encodes H.264. Sound is beat-synced sound effects plus BGM composed in code from a chord progression and played with FluidSynth. Flow: rough notes or a brief → feasibility test of hard scenes → cut sheet (first/last frame per cut + FB column) iterated with a human by version → human OK → final render → 9:16 / 1:1 / 16:9 in that order. Always use it for "make a video", "intro video", "promo video", "motion graphics", "motion design", "animated video", "logo animation", "vertical video", "for Reels / Shorts", "animate these screenshots", "export to mp4", "storyboard", "cut sheet", "add BGM to the video", or in Japanese 「動画を作って」「紹介動画」「プロモ動画」「モーショングラフィックス」「モーションデザイン」「アニメーション動画」「ロゴアニメ」「縦動画」「リール / ショート用」「スクショを動かして見せたい」「mp4 で書き出して」「絵コンテ」「カット表」「動画に BGM を付けて」. It does not do generative-AI live-action video or narration audio, and does not call image-generation APIs (it lists the images it needs and accepts images a human made elsewhere as assets).
---

# motion-video

Write the video as "a function that draws the frame at time t", then capture it frame by frame into an mp4.
Unlike generative-AI video, **the same input gives the same mp4 every time** (hashes match), you can fix just the one frame that bothers you, and there is no extra cost.

- Engine: `scripts/render.mjs` (zero dependencies; node 22+ (uses the global WebSocket) / Google Chrome or Chromium / ffmpeg). Sound: `scripts/audio.mjs` (sound effects, mixing, mastering) and `scripts/music.mjs` (BGM composition and playback)
- Authoring reference: `references/authoring.md` (the video.js contract, API, re-layout per aspect, sound, loops)
- Installing the BGM soundfont and impulse responses, and their licenses: `references/audio-assets.md`
- Entry point (rough notes / brief template): `references/brief-template.md` / music brief: `references/music-brief.md` / self-review: `references/self-review.md`
- Example brand settings: `references/brand.example.json`

## Prerequisites

- **Chrome does not start inside Claude Code's Bash sandbox** (mach bootstrap is denied). Run `render.mjs` and `evals/run.sh` with `dangerouslyDisableSandbox: true`.
- `$TMPDIR` differs inside and outside the sandbox. Pass absolute paths. The working PNG sequence goes to `os.tmpdir()/motion-video/`.
- If Chrome is not in the standard location, pass `MOTION_VIDEO_CHROME=<executable>`.
- Only when using BGM (`meta.audio.music`) you need FluidSynth (`brew install fluid-synth`) and a soundfont (default `~/.local/share/motion-video/soundfonts/GeneralUser-GS.sf2`). Without them it stops with an error. See `references/audio-assets.md` for installation.
- Keep the project (video.js, assets, exports) outside the skill (e.g. `tmp/` of the repository you are working in). Do not put videos or images in the skill's repository.

Below, `R=${CLAUDE_PLUGIN_ROOT}/skills/motion-video/scripts/render.mjs`.

## Steps

### 1. Entry: rough notes or a brief

Pick an entry point from `references/brief-template.md`.
**The default is "start from rough notes"**: ask the human only for the impression, rough notes per scene and the asset list; the agent proposes the cut breakdown (the first cut sheet) and a music brief (`references/music-brief.md`, when adding BGM) first, and the human corrects them. Handing over a blank template stalls people.
Add an instruction of this kind: "The ideas are hints. Don't aim to reproduce them. Over-the-top expression is fine."
If the human wants to write a brief, copy the template as `brief.md` and fill it in. Fill only undecided items by asking (up to 3 questions at a time, in the order at the end of the template).

**Settle the asset list first.** If the product UI, numbers or claims do not exist as real material, do not make them up; ask the human for them (do not build a video on fabricated screens or numbers).
Judging asset rights (whether a photo or logo may be used) is outside this skill. Ask the human.
If textures or live-action footage are needed, hand the human an **asset request list** (category / stock ID or search terms / content / where it is used); if assets that look flat when drawn in code (signs, labels) are needed, hand over a **list of required images** (count, size, purpose, prompt in the five-section structure) (sections 13 and 14 of `references/authoring.md`). Downloading, generating and judging rights are done by the human.

### 2. Feasibility-test difficult scenes first

For scenes that use many live-action clips, heavy compositing or heavy drawing (many particles, several stacked textures), prototype just that scene before v1.
Write the prototype in the same `video.js` form as production, draw it with `node $R stills <project> --times <sec,…>` and look at it with Read. Drawing time is the stills run time divided by the number of frames (draw 10 or more frames to amortize Chrome's startup).
Write the results per scene in `verify.md`:

```markdown
| Scene | Verdict | What to build and how | Needs | Draw time per frame |
|---|---|---|---|---|
| s3 | ● feasible | Swap 3 live-action clips with springTrack | clips/a.mp4 etc. | 0.18 s |
| s5 | ▲ risky (with a mitigation) | Overlay a crack texture with screen. Pattern on edges → alpha 0.2 | assets/tex/crack.jpg (requested) | 0.31 s |
| s6 | ○ untested | 300 shards | — | — |
```

If ▲ or ○ remain, or drawing is too slow (the final render draws duration × fps × 4 subframes), **you may change the structure based on the results** (split cuts, drop textures, shorten). Tell the human if you change it.
Writing the key points with the same symbols in a scene's `verify` field shows them in the cut sheet's Verify column.

### 3. Draft the cut sheet

1. Read `references/authoring.md` and write `video.js`. `meta.scenes` becomes the cut sheet as is (1 scene = 1 cut: what to convey, picture, motion, text, sound, transition, verify). Read the brand from brand.json; do not hard-code colors.
2. Export the storyboard:
   ```bash
   node $R storyboard <project> --aspect all
   ```
   The main output is `out/storyboard/cutsheet.html` (the **cut sheet**: 1 row = 1 cut, pictures are the "first" and "last" frames, start and length in seconds and beats, a Verify column, a yellow FB column). It also writes `storyboard.md` (scene table and warnings) and, per aspect:
   - `cuts/<cut>-start.png` / `-end.png` (the two frames in the cut sheet) and a representative frame per scene
   - `contact.png` (one frame per beat) / `strip.png` (12 frames around the fastest motion) / `phone.png` (shrunk to a 390px phone width) / `seam.png` (loops only)
   - `beats.json` (beats, bar starts, peaks)
   - for videos with sound, `audio/`: `preview.wav` (mixed with the same steps as the final) / `spectrogram.png` (white lines = scene boundaries, green lines = peaks) / `audio.json` (LUFS, true peak, RMS per band) / `bgm.mid` (when there is BGM)
   - the result of the determinism check (draw the same frame twice and compare hashes)
3. **Clear every warning** (blank scene-contract fields, hard cuts, stretches of 4+ seconds without change, sound effects off the beat, missing fonts, failed determinism check, FB without a response). For warnings you cannot fix, give the reason when showing the human.

### 4. Self-review → FB round trips on the cut sheet → human OK

Score the 9 items in `references/self-review.md` (hook, readability on a phone, motion quality, visual change, composition, brand accuracy, sound sync, genericness, pacing contrast) from 1 to 10 **by actually looking at the output PNGs with Read**.
Name the worst 3 with timestamps, fix them, and redraw just those seconds to confirm (`node $R stills <project> --from 4.0 --to 4.5`). Repeat until every item is 8 or higher.

For videos with sound, also look at `audio/spectrogram.png` with Read: check that the music's climax lands on a green line (peak) and that sound effects and BGM do not clash in the same band, and use the per-band RMS in `audio.json` to check for a muddy low end (if low is louder than lowmid it is leaning muddy; the bottom row of the spectrogram blurs on the log axis, so judge by the numbers).

Then show the human cutsheet.html and the scores, and if there is sound, have them listen to `audio/preview.wav`, and **always stop here**. If the human is not there, wait (do not approve on your own).

The human replies in one of two ways:

- **FB**: the human writes in the cut sheet's FB column and "Save FB" puts `feedback/v<N>.json` in the project (format: "12. Cut sheet and FB round trips" in `references/authoring.md`). The agent fixes each FB item and **writes the response in `response` and what changed in this version in `summary` of the same file** before running storyboard. The version moves to v<N+1>, the previous version stays in `out/storyboard/v<N>/`, and the top of the cut sheet shows a "Responses to v<N> FB" table and before/after comparison images for the cuts that had FB. A missing response becomes a warning. Redo the self-review, show it again and stop
- **OK**: record that statement and approve:

```bash
node $R approve <project> --by "<person who gave the OK>" --note "<the OK statement verbatim>"
```

`approve` passes only when the hash of the current sources (video.js, assets, brand.json, feedback/) matches the hash at the time the storyboard was made.

### 5. Final render

```bash
node $R final <project>            # every aspect in meta.aspects
node $R final <project> --aspect 9:16
```

- With no approval, or if the sources changed by even one byte after approval, it stops with exit 3. After fixing, go back to step 3 and get the OK again (this mechanism makes it impossible to quietly fix and ship after approval).
- The determinism check runs again before rendering. 60fps (meta.fps), motion blur with 4 subframes, H.264 / yuv420p / CRF 16, AAC 192kbps audio. Sound (SFX only or with BGM) is mastered to -14 LUFS ±1 with true peak at or below -1 dBFS, and the values re-measured on the mp4 with ebur128 go into the README and manifest.
- Deliverables go to `out/deliver/`: per aspect `final.mp4` / `poster.png` / `contact.png`, `source/` (all sources and approval.json), `README.md`, `manifest.json` (hashes, probe, loudness, BGM record (style, soundfont sha256, MIDI sha256), assets drawn).

After rendering, self-review again (look at poster.png and contact.png with Read). If something needs fixing, go back to step 3.
When handing over the result, show the mp4 and poster as clickable links.

### 6. Line up the aspects

**Make 9:16 first**, then re-lay out 1:1 and 16:9 from the same timeline (the same video.js). Do not crop a landscape master.
Re-layout uses layout functions (`u` / `safe` / `split` / `grid` / `orient` in `ctx.L`), not fixed pixels. Set `meta.aspects: ['9:16', '1:1', '16:9']`, check the frames of every aspect with storyboard `--aspect all`, then get approval.

## Other commands

| Command | Purpose |
|---|---|
| `node $R check <project> [--frame 300]` | Compare the same frame "drawn first" and "drawn after other frames". For loops, also the continuity of the seam |
| `node $R stills <project> --times 1.2,3.4` / `--from a --to b` | Redraw only those seconds (`out/stills/<aspect>/`) |
| `node $R probe <file.mp4>` | Resolution, fps, frame count, duration, audio, sha256 |
| `node scripts/audio.mjs --duration 6 --cues cues.json [--music music.json --scenes scenes.json --peaks 4] --out x.wav [--spectrogram x.png]` | Build only the sound with the same steps as the final and listen (no Chrome, works inside the sandbox) |
| `node scripts/music.mjs --duration 8 --bpm 120 --progression Am,F,C,G --style calm --out bgm.wav` / `--styles` | Play only the BGM (before effects) / list the styles |

## Out of scope

- Generative-AI live-action video (Gemini etc.), generative-AI music, paid narration audio, and calling external APIs in general (including searching and downloading stock assets)
- Calling image-generation APIs from the skill. The skill's job ends at producing the list of required images (with prompts); generation happens outside the skill after the human approves, and the resulting images come back as assets
- Judging asset rights and downloading (the skill outputs an asset request list; the human decides and places the files)
- three.js / WebGL 3D, depth estimation from photos, turning it into an interactive website
- DOM / CSS animation (only what is drawn on the canvas is captured)

## Limits

- Hash matching holds only on "the same machine, the same Chrome, the same ffmpeg, the same FluidSynth and soundfont". Upgrading any of them can change frame pixels or sound. The soundfont lives outside the project, so it is not part of the approval hash (its sha256 is kept in the manifest).
- BGM is two styles (calm / upbeat) with fixed arrangement patterns and no melody. Whether the music is good is decided by a human listening to preview.wav. Adding BGM to a loop causes a dip in the sound at the seam because of the final fade.
- Fonts are whatever is on the system unless `fonts.*.file` is passed in brand.json. If missing, it draws with a fallback and storyboard warns.
- Long live-action clips keep every frame in memory. Limit them with `meta.clips.*.maxWidth` and fps.

## eval

```bash
sh ${CLAUDE_PLUGIN_ROOT}/skills/motion-video/evals/run.sh            # outside the sandbox; takes a few minutes
sh ${CLAUDE_PLUGIN_ROOT}/skills/motion-video/evals/run.sh --only media-mix-image-and-clip-30fps
```

Actually renders the 6 cases in `evals/evals.json` (a 15-second 16:9 intro of the fictional Example Co. / images + live-action clip at 30fps / a 9:16, 1:1, 16:9 loop / 8 seconds with BGM / cut sheet and FB round trip (v1→v2) / negative contract cases), grades them mechanically, and outputs `pass_rate` and per-case `grading/<name>.json` (skill-creator's grading format: text / passed / evidence). Outputs go to `--work` (default `os.tmpdir()`).
