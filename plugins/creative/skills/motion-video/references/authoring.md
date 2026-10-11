# Writing video.js (render contract and API)

Contents: 1. Project layout / 2. meta / 3. The render(ctx, t) contract / 4. ctx / 5. Motion helpers (ctx.M) / 6. Drawing helpers (ctx.D) / 7. Re-layout per aspect / 8. Assets, clips and fonts / 9. Sound / 10. Loops / 11. Visual defaults / 12. Cut sheet and FB round trips / 13. Layering live-action textures / 14. Accepting generated images as assets

## 1. Project layout

```
<project>/
├── brief.md          brief or rough notes (references/brief-template.md)
├── music-brief.md    music brief (when adding BGM. references/music-brief.md)
├── verify.md         feasibility test notes (when there are hard scenes. Step 2 in SKILL.md)
├── video.js          exports meta and render(ctx, t) (this is what you write)
├── brand.json        colors, typefaces, logo (if absent, pass one in with --brand. Example: references/brand.example.json)
├── assets/           images (PNG / JPG / SVG / WebP)
├── clips/            live-action clips (mp4 etc. Anything ffmpeg can read)
├── feedback/         v<N>.json = the human's FB on version N and the agent's responses (12.)
├── approval.json     written by the approve command (do not create by hand)
└── out/              output (storyboard/ stills/ deliver/)
```

Put it outside the skill (e.g. `tmp/` of the project you are working in). Do not put videos or images in the skill's repository.

## 2. meta

```js
export const meta = {
  title: 'Example Co. intro',
  duration: 15,            // seconds. Make duration × fps an integer
  fps: 60,                 // default 60
  aspects: ['9:16', '1:1', '16:9'],  // first one is the primary aspect (storyboard default). Build 9:16 first
  loop: false,             // true for a looping piece (the seam is checked for continuity)
  poster: 13.8,            // time used for poster.png (default: representative frame of the last scene)
  subframes: 4,            // number of motion-blur subframes (default 4)
  shutter: 0.5,            // shutter angle (fraction of one frame's time to blend. Default 0.5 = 180°)
  assets: { shot: 'assets/dashboard.png' },            // ctx.img('shot')
  clips: { demo: { src: 'clips/demo.mp4', fps: 30, maxWidth: 1280 } },  // ctx.clip('demo', seconds)
  scenes: [ /* scene contract. See below */ ],
  audio: { bpm: 120, offset: 0, beatsPerBar: 4, peaks: [0, 12], cues: [ /* 9. Sound */ ] },
};
```

### Scene contract (each element of scenes)

```js
{
  id: 's2', start: 3, end: 6,       // seconds. Lay them out from 0 to duration with no gaps or overlaps
  key: 4.8,                          // time of the representative frame (default: the middle). For several: keys: [3.6, 5.2]
  message: 'What to convey (one sentence)',
  screen: 'Screen: composition, objects, camera',
  motion: { enter: 'enter', main: 'main action', secondary: 'secondary action', exit: 'exit' },  // a string also works
  narration: 'One sentence of narration (no voice is generated. Used as captions or a script to read)',
  text: 'Text shown on screen (if omitted, the cut sheet Text column shows narration)',
  sound: 'sound',
  transition: 'How an object on screen turns into an object of the next scene',  // "cut" triggers a warning
  energy: 0.8,                       // optional. BGM layer density 0..1 (default depends on whether the scene is a peak / first / last scene. 9. Sound)
  verify: ['● surface morph looks feasible with springTrack', '▲ in 9:16 the right card cuts into the safe area (plan: shrink it)'],  // optional. The cut sheet Verify column (12.)
}
```

storyboard turns these fields directly into the scene table and the cut sheet (1 scene = 1 cut). Blank fields, gaps and hard cuts show up as warnings (`text` and `verify` do not warn when empty).

## 3. The render(ctx, t) contract

`render(ctx, t)` is **a pure function where time t alone determines a frame** (seek(t)). Frame 812 draws correctly without drawing 0–811.

- Forbidden: carrying state over from the previous frame (accumulating positions in a module variable, etc.) / timers, requestAnimationFrame / CSS transitions, DOM animation (only the canvas is captured) / `Math.random`, `Date.now`, `performance.now` (they throw during rendering)
- For randomness, create `ctx.M.rng(seed)` on the spot and use it (draw from the same seed every frame)
- Every frame, the harness clears the canvas and resets transform and alpha before calling. Paint the background yourself
- The `check` command compares "the first time a frame is drawn" with "after drawing other frames" and fails if they differ
- It may be async (all assets are preloaded, so synchronous is usually enough)

## 4. ctx

| Name | Contents |
|---|---|
| `g` | CanvasRenderingContext2D |
| `W`, `H` | Pixels of the aspect (16:9=1920x1080 / 9:16=1080x1920 / 1:1=1080x1080 / 4:5=1080x1350) |
| `L` | Layout (7.) |
| `M` / `D` | Motion helpers / drawing helpers |
| `brand` | Contents of brand.json (`brand.colors.primary` etc.) |
| `meta`, `fps`, `duration` | Values from meta |
| `beats` | `M.beatGrid(meta.audio.bpm, …)` |
| `font(role, size, weight=700)` | CSS font string for brand.fonts[role] (fallback included) |
| `img(key)` | Asset image. `'@logo'` is the logo in brand.json |
| `clip(key, seconds, { loop })` | The clip's frame at that second (an image) |
| `scene(t)` | Scene at t `{ id, start, end, local, p }` (p = progress within the scene 0..1) |
| `text(str, x, y, opts)` | Text (with wrapping and line-break rules). opts: font, color, align, baseline, maxWidth, lineHeight, letterSpacing, alpha |
| `image(img, box, opts)` | Image into a box (opts: fit 'contain'/'cover', radius, alpha) |

## 5. Motion helpers (ctx.M)

- `spring(t, preset)` — a 0→1 spring (closed-form, an exact analytic solution). 0 for t<=0
  - `snappy` (k260/d24, buttons, toggles) / `default` (k170/d26, cards, camera, text) / `playful` (k130/d18, mascots) / `heavy` (k120/d30/m2.5, large surfaces. The skill's own guessed values)
  - UI may overshoot slightly (snappy / playful). **Text must not overshoot** (default / heavy)
- `springTrack(t, keys, preset)` — adds one spring each time the target changes. `keys = [{t:0,v:0},{t:1.2,v:100},{t:3,v:40,preset:'snappy'}]`. Value and velocity stay continuous even when the destination changes mid-way
- `springDuration(preset)` — seconds until it settles (for estimating scene length)
- `progress(t, a, b)` (normalized to 0..1) / `ease.outCubic` etc. / `lerp` / `clamp` / `stagger(start, i, gap)`
- `beatGrid(bpm).beat(n)` / `.bar(n, b)` / `.nearest(t)` — times of beats and bar starts
- `rng(seed)` / `mixColor(a, b, p)` / `withAlpha(hex, a)`

Order of text and container (the playbook pattern):

```js
const out = M.ease.inCubic(M.progress(t, end - 0.45, end - 0.2)); // text exits before the morph
const box = M.springTrack(t, [{ t: 0, v: A }, { t: end - 0.15, v: B }]);  // the container morph starts a little before the boundary
const inn = M.spring(t - (end + 0.15), 'default');                  // new text enters after the morph has started
```

## 6. Drawing helpers (ctx.D)

`D.fill(g, W, H, color)` / `D.roundRect(g, x, y, w, h, r)` (only builds the path. Do fill/stroke/clip yourself) / `D.text(g, …)` / `D.image(g, …)` / `D.wrapLines(g, text, maxWidth)`

## 7. Re-layout per aspect

Do not place things in fixed pixels. Place them in units of `L = layout(W, H)`:

- `L.u` — 1% of the short side. Text size, margins and corner radii are multiples of it (`6 * L.u` etc.)
- `L.orient` — `'landscape' | 'portrait' | 'square'`. Use it to branch the arrangement
- `L.safe` — the safe area 6% in from the edges `{x, y, w, h}`. Keep text inside it
- `L.split(gap)` — split in two: left/right if landscape, top/bottom if portrait
- `L.grid(cols, rows, gap, box)` — grid cells
- `M.fit(iw, ih, box, 'contain'|'cover')`

Lay out 9:16 first, then check with storyboard `--aspect all` that the same function holds up in 1:1 and 16:9. Do not crop a landscape master.

## 8. Assets, clips and fonts

- Images: register in `meta.assets` → `ctx.img(key)`. Everything is loaded before frame 1 is drawn, so no load waiting is needed
- Always write `width` / `height` attributes on SVGs (without them Chrome renders at 300x150 or similar)
- Live-action clips: **do not use the browser's `<video>`**. render.mjs uses ffmpeg to split them into numbered frames at `meta.clips.*.fps` and caches them; `ctx.clip(key, seconds)` returns the frame at that second. Shrink long footage with `maxWidth` (all frames are held in memory)
- Fonts: pass a font file (path relative to brand.json; variable fonts are fine) in brand.json's `fonts.<role>.file` and it is loaded via @font-face. Otherwise the family name is looked up in the system, and failing that the fallback is used (storyboard warns)
- Judging asset rights (whether a photo or logo may be used) is outside this skill's scope. A human checks it in the brief's asset list

## 9. Sound

Sound has two layers: "sound effects (cues)" and "BGM (music)". With neither, the mp4 is silent; without `music` it runs on sound effects alone (no FluidSynth or soundfont needed).

```js
audio: {
  bpm: 120, offset: 0, beatsPerBar: 4,
  peaks: [0, 12],                       // the hero's entrances (put them on bar starts). The BGM peaks align here too
  cues: [
    { bar: 0, sfx: 'thump' },           // bar start
    { beat: 6, sfx: 'whoosh', gain: 0.6 },
    { t: 3.5, sfx: 'pop', pan: -0.3 },
    { t: 3.62, sfx: 'click', offbeat: true },  // be explicit when off the beat
  ],
  music: {                              // omit for sound effects only
    progression: ['Am', 'F', 'C', 'G'], // chord progression (repeats)
    style: 'calm',                      // calm / upbeat
    chordBars: 1,                       // how many bars each chord lasts (0.5 = two per bar)
    seed: 1,                            // random seed for velocity and timing variation (change it for another take)
    humanize: 1,                        // amount of variation (0 = none)
    gainDb: 0,                          // BGM level relative to sound effects (+ raises BGM)
    duck: 5,                            // how strongly BGM dips when a sound effect plays (sidechain compression ratio. 1 = no dip)
    reverb: 0.3,                        // reverb mix (0..1)
    reverbSeconds: 1.6,                 // length of the synthetic impulse response
    // ir: 'ir/hall.wav',               // to use a measured impulse response (path relative to the project)
    // soundfont: 'sf/other.sf2',       // to change the instrument source (default below)
  },
}
```

### Sound effects

`click / pop / thump / whoosh` (synthesized in code in scripts/audio.mjs, fixed seed). storyboard warns about cues off the beat and peaks off bar starts.

### BGM (compose → play)

- **Compose** (scripts/music.mjs): writes MIDI (SMF) in code from the chord progression and style, on the beat grid (bpm, offset, beatsPerBar). No generative AI
- **Styles**
  - `calm`: pad (GM 89 Warm Pad) + piano arpeggio (GM 0) + bass (GM 32). No drums. Quarter notes at low energy, eighths at high energy; peak bars mix in an octave up
  - `upbeat`: drums (ch10) + eighth-note bass (GM 33) + electric piano offbeat stabs (GM 4) + a thin pad. A snare fill in the bar before a peak, a crash on the peak bar start
  - In both, the pad swells (CC11) in the bar before a peak, and the last bar holds the chord to the end
- **Arrangement comes from the scene table**: each bar's energy (0..1) comes from that scene's `energy` field (takes priority if written) or the default (scene containing a peak 1.0 / first 0.45 / last 0.7 / others 0.65), and layers are brought in and out accordingly. The visual peaks (`peaks`) and the music's peaks fall on the same bars
- **Variation**: a random generator with fixed `seed` varies note velocity by ±8 and timing by ±2% of a beat (pad chords, bar-start kicks, peak crashes and the very first beat are not shifted in timing, only in velocity)
- **Playback**: FluidSynth plays a soundfont (default `~/.local/share/motion-video/soundfonts/GeneralUser-GS.sf2`; looked up in the order `music.soundfont` → env var `MOTION_VIDEO_SF2` → default) at 48kHz, 32-bit float. FluidSynth's internal reverb and chorus are off (ambience is added on the ffmpeg side). Installation and license: `references/audio-assets.md`
- With the same MIDI, same soundfont and same FluidSynth version, the rendered WAV is cached in the working folder

### Mixing and mastering (same steps in final and storyboard)

1. BGM: cut below 50Hz → -3dB at 250Hz → -2dB at 3kHz (to leave room for the sound effects' band) → light compression → convolution reverb (`afir`. The impulse response is synthetic with a fixed seed by default; replace it with a measured one via `music.ir`) → stereo widening (`stereowiden`) → fade the last 0.5 seconds
2. Normalize BGM to -20 LUFS (+`gainDb`), and mix it in, dipping BGM only when a sound effect plays (`sidechaincompress`)
3. Set the overall gain and catch peaks with a 4× oversampled limiter (`alimiter`, ceiling -2 dBFS). Measure and tighten the gain until it lands within -14 LUFS ±0.2
4. Encode with the delivery settings (AAC 192kbps) and measure; if true peak exceeds -1 dBFS, lower the limiter ceiling and redo

The result is -14 LUFS ±1 and true peak at or below -1 dBFS (the same for videos with only sound effects. Sparse sound effects alone get squashed hard by the limiter to reach it, so listen to preview.wav to check).
BGM fades out over the last 0.5 seconds, so adding BGM to a looping piece (`meta.loop: true`) makes the sound dip once at the seam. final re-measures the mp4 audio with ebur128 and writes it to the README and manifest.

### Listening and looking at the storyboard stage

storyboard writes the following to `out/storyboard/audio/` (only for videos with sound):

- `preview.wav` — the sound mixed with the same steps as the final. Hand it over together with the storyboard so people listen to it
- `spectrogram.png` — spectrogram with a logarithmic frequency axis. White lines are scene boundaries, green lines are peaks. **Look at it with Read** to check that the music's peaks land on the peaks and that sound effects and BGM do not collide in the same band
- `audio.json` — loudness (LUFS), true peak (WAV and after AAC), loudness range, RMS per band (sub <40Hz / low 40–120 / lowmid 120–500 / mid 500–4k / high >4k). The bottom of the spectrogram bleeds on the log axis and looks brighter than it is, so judge low-end muddiness by the per-band RMS (if low is larger than lowmid, it is on the muddy side)
- `bgm.mid` — the composed MIDI (open it in a DAW to check)

Try it standalone (no Chrome needed, so it runs inside the sandbox):

```bash
node scripts/audio.mjs --duration 8 --bpm 120 --cues cues.json --music music.json --scenes scenes.json --peaks 4 --out /tmp/mix.wav --spectrogram /tmp/spec.png
node scripts/music.mjs --duration 8 --bpm 120 --progression Am,F,C,G --style upbeat --out /tmp/bgm.wav   # BGM only (before effects)
node scripts/music.mjs --styles
```

## 10. Loops

With `meta.loop: true`, check and storyboard compare "the change from the last frame → the first frame" with "the change between adjacent frames". It fails unless both position and velocity connect.
Write motion with periodic functions like `Math.sin(2π t / duration)`. Just wrapping with `t % duration` does not fix it (it still jumps at the seam).

## 11. Visual defaults

- Forbidden: a centered title on a gradient background / fade everything in / corner labels / outlines / glow
- A new visual event every 2–4 seconds (storyboard warns about "stretches with no noticeable change")
- Transitions take the form of an object on screen turning into an object of the next scene (a surface shrinks into a pillar, a card becomes the next card)

## 12. Cut sheet and FB round trips

`storyboard` writes `out/storyboard/cutsheet.html` (static HTML, images by relative path). One row = one cut (= one scene); the picture is two frames, the "first frame" (the cut's first frame, `start`) and the "last frame" (its last frame, `end - 1/fps`), and motion is described in prose.

- Header: `CUT SHEET v<N>`, the `summary` from the previous version's FB file (what changed in this version), chips (BPM / bars = seconds / number of cuts / resolution · fps / asset count), warnings
- Project info: project name / total length / tempo, BPM / aspect ratio / deliverables / reference (`meta.reference`) / colors, fonts (brand.json)
- Timeline strip: one cell = one bar, scenes as color bands, cut numbers below
- The "Responses to v<N-1> FB" table (version 2 onward): Target / FB / Response / Cut (comparison image)
- Cut sheet columns: No. / Start (s · beat) / Length / First frame / Last frame / (if there are several aspects) Other aspects (first) / Picture (message + screen) / Motion / Transition to next / Text / Sound / Verify (`verify`) / FB (yellow input field)
- Start and length are shown in both seconds and beats (from the same bpm, offset and beatsPerBar as `beats.json`. Example: at 120 BPM, 9.5 seconds = bar 5 beat 4 (19 beats))

Images are `out/storyboard/<aspect>/cuts/<cut ID>-start.png` / `-end.png`.

### Verify column (written by the agent)

The scene's `verify` (an array of strings, or a newline-separated string). The leading symbol sets the color:

- `●` done / looks feasible / `▲` risk, unresolved (write the countermeasure) / `◆` asset, next step / `✓` confirmed / `○` not yet verified

### FB file

The human looks at the version N cut sheet and writes `feedback/v<N>.json` (the cut sheet's "Save FB" button saves what was typed in the FB column in this form):

```json
{
  "cuts": {
    "s2": "The card comes in too early. Delay it by one beat",
    "s4": { "fb": "Make the number bigger", "response": "Scaled the number by 1.4x" }
  },
  "overall": "I'd like a bit more whitespace overall",
  "summary": "(written by the agent) One paragraph on what changed in the next version"
}
```

- Keys are cut IDs (the scene `id`). Values are a string (FB only) or `{ fb, response }`, or an array for several. `overall` is FB on the whole
- **The agent writes its responses in the same file**: turn each string FB into `{ "fb": "…", "response": "…" }` and write a summary of the version in `summary`
- The version number is "the latest version that has an FB file + 1" (v1 if there is no FB). Re-running without FB does not advance the version; it rebuilds the same version
- `storyboard` builds the latest version directly under `out/storyboard/` and keeps a copy in `out/storyboard/v<N>/`. The previous version's `v<N-1>/` is not deleted (so v1 and v9 can be compared side by side)
- From version 2 onward, for cuts with FB, it writes a comparison image putting the previous and current versions' first frame / last frame side by side (top row = previous version, bottom row = current version) to `out/storyboard/compare/<cut ID>-v<N-1>-v<N>.png`
- Warnings: FB with no response (`response`) written / FB on a cut ID not in the current scene table / no frames from the previous version, so no comparison can be made

`feedback/` is inside the project, so **it is part of the approval hash**. If FB was added but storyboard was not re-run, `approve` stops with "the source has changed" (you cannot approve without reflecting the FB). After writing the responses, re-run storyboard before showing it.

When FB needs evidence ("it stutters here" etc.), render that stretch finely and compare old and new: run `node <skill>/scripts/render.mjs stills <project> --from 13.3 --to 15.0` for each version and compare `out/stills/<aspect>/sheet.png`.

## 13. Layering live-action textures

Drawing everything in code gives a "CG-like cleanness". Layer live-action textures thinly to add tactility.

| Category | Example | Where to use | Blending |
|---|---|---|---|
| Glass cracks | Photo of broken glass (white cracks on black) | Only one cut, for an impact or transition | `screen` (only the white cracks show) |
| Risograph grain, misregistration | Scan of a riso print, two-color misregistration | Paper texture on surfaces and large text | `multiply` (the grain dirties the surface). For misregistration, offset the same surface by 1–2px in a second color |
| Halftone | Enlarged print halftone dots | Instead of photo assets or gradients | `multiply` or `overlay` |
| Glass smudges, fingerprints | Dirt on window glass (on black) | A through-the-screen or through-the-lens feel | `screen`, alpha 0.1–0.3 |
| CRT phosphors | Close-up of CRT RGB phosphors | Cuts showing a screen or UI | `multiply` or `overlay`; scale it up so the stripes are not prominent |

How to blend (register in `meta.assets` and use `ctx.img`):

```js
g.save();
g.globalCompositeOperation = 'multiply';   // screen / overlay / soft-light etc.
g.globalAlpha = 0.35;
ctx.image(ctx.img('riso'), { x: 0, y: 0, w: W, h: H }, { fit: 'cover' });
g.restore();
```

- Pasting the same image every frame looks frozen. To move it, switch position and angle per bar with `M.rng(seed)` (per-frame randomness does not break determinism, but it flickers)
- The harness resets the blend mode to `source-over` every frame, but wrap it in `save` / `restore` anyway
- **Layered assets can produce patterns around edges** (common with lens-smudge types). After layering, re-render those seconds with `node <skill>/scripts/render.mjs stills <project> --from a --to b` and look with Read. If patterns appear, lower the alpha or drop that asset
- Remove textures that are not working rather than adding more (`self-review.md`'s "genericness" and "pacing contrast")

### Asset request list

For textures and live-action assets, the agent produces an **asset request list**, and **the human handles downloading and rights decisions**. The skill does not call external APIs (it does not search or download from stock sites either).

| Category | Stock ID or search terms | Contents | Where to use (cut) | Location |
|---|---|---|---|---|
| Risograph grain | `risograph grain texture` | Coarse grain on white, A4-scan equivalent | surfaces in s1, s5 | assets/tex/riso.jpg |
| Glass smudge | `glass smudge black background` | White smudges on black | through-the-screen in s3 | assets/tex/smudge.jpg |

Once the human has placed them, add them to `meta.assets` and write in the cut sheet Verify column, e.g. `◆ waiting for riso.jpg` → `✓ riso.jpg applied`.

## 14. Accepting generated images as assets

The skill itself does not call image generation. For assets that look flat when drawn in code (signs, labels, packaging, hand-drawn props, etc.), produce a **list of required images** and hand it to the human:

| Key | Count | Size | Purpose (cut) | Prompt |
|---|---|---|---|---|
| sign | 1 | 1600×900, PNG, transparent background | storefront sign in s2 | five-section structure (below) |

Write prompts in the five-section structure (Scene / Subject / Important details / Use case / Constraints. Do not leave Constraints empty). If the same plugin's `image-generation-prompt` skill is available, build them with it.

Generation happens outside the skill, **after getting the human's approval** (via a route the human picks, such as codex). Put the resulting images in `assets/` like any other asset and add them to `meta.assets`. Do not generate product UI, numbers or logos (ask the human for the real thing).
