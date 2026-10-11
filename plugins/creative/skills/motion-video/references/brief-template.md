# Brief (project plan) template

The first page of making a video. There are two entry points.

- **Start from rough notes** (default): the human hands over only an impression, rough notes per scene and an asset list. The agent proposes the cut breakdown (the v0 cut sheet) and the music brief first, and the human corrects them. Handing someone a blank template stalls them, so recommend this one first
- **Fill in the brief**: the human writes the template below, or the agent fills it in by asking questions

## Start from rough notes

Ask the human for only these three things:

```markdown
## Impression
[e.g. Starts quiet, opens up just once at the final logo. A tactile, papery feel]

## Rough notes per scene
- [e.g. Open with the problem in big type]
- [e.g. The admin screen assembles itself]
- [e.g. End on the logo]

## Asset list
- [e.g. assets/dashboard.png screenshot of the admin screen (as of 2026-09)]
- [e.g. clips/demo.mp4 screen recording of the workflow, 12 seconds]
```

Attach this framing to the instructions for the agent (if the human does not write it, the agent imposes it on itself):

> The ideas are hints. Do not aim to reproduce them. Overdoing the expression is fine.

On receiving them, the agent:

1. Proposes a cut breakdown. Write `meta.scenes` in `video.js` with one cut per row; render can stay provisional (just surfaces and text). Show the first cut sheet (v1) produced by `storyboard` as a starting draft before the human corrects it
2. Fills in the music brief (`music-brief.md`) and shows it alongside. Note any fields that do not map to `music.mjs`
3. Asks questions only for items that cannot be decided from the rough notes (length, aspect, audience, CTA) (see "Asking questions to fill missing items" below). Do not invent UI or numbers that are not in the assets; ask the human for them
4. Takes the human's corrections in the cut sheet's FB column (`authoring.md`, "12. Cut sheet and FB round trips")

If the human has a finished picture in their head, the more completely they write it down, the better the result. If they cannot picture it yet, tell them this is the stage to think it through together with the agent, using the cut sheet as a draft.

## Brief template

The human may write it, or the agent may fill it in by asking questions.
**Write in the order "logline and constraints → look → tools"**. Do not talk about color or motion before what, for whom and how many seconds are decided.

Put it in the project folder as `brief.md` (it goes as-is into `source/` in the `final` deliverables).

```markdown
<role>
You are a motion designer. You make one short video by drawing it frame by frame in code.
</role>

<purpose>
- Logline (one sentence): convey [what] to [whom] so that they [do what]
- Audience: [e.g. owners of small businesses, skimming the X timeline on a phone in portrait]
- Length: [e.g. 15 seconds] / Aspect: [e.g. 9:16 first, then 1:1 and 16:9 from the same timeline] / fps: 60
- Action after watching (CTA): [e.g. open the website]
- Constraints: [e.g. understandable without sound / do not show features or numbers that do not exist]
</purpose>

<visual_identity>
- Path to brand.json: [e.g. ~/brand/example/brand.json] (colors, typefaces, logo)
- Tone: [e.g. clear, positive, generous whitespace]
- Reference material: [URLs or files] → **carry over only the grammar** (use of color, typesetting, length, transitions, camera).
  **Do not carry over the content** (story, logos, characters, composition of copyrighted works)
- Forbidden by default: a centered title on a gradient background / fade everything in / corner labels / outlines / glow
</visual_identity>

<story>
Scene order (for a product video, five beats is the default):
1. Problem — big type, about five words
2. The actual UI assembles itself
3. Three features shown through actual operation
4. One verified number (cite the source)
5. Logo + CTA

Asset list (finalize before writing animation. **Do not fabricate product UI or claims**):
| Key | File | What it is | Scenes used |
|---|---|---|---|
| shot | assets/dashboard.png | Screenshot of the admin screen (as of 2026-09) | 2, 3 |
| demo | clips/demo.mp4 | Screen recording of the workflow, 12 seconds | 3 |
| @logo | logo in brand.json | Logo | 5 |
</story>

<motion>
- Springs: UI (cards, buttons) uses snappy / playful (slight overshoot is fine); text and large surfaces use default / heavy (no overshoot)
- Text in and out: text exits before the container morphs, and new text enters after the morph has started
- Add a new visual event every 2–4 seconds
- Transitions: an object on screen turns into an object of the next scene (no hard cuts)
- Looping piece: [yes / no] (if yes, position and velocity connect from the last frame → the first frame)
</motion>

<audio>
- BPM: [e.g. 120]. Put state changes on beats and the hero's entrance on bar starts
- Sound effects: click / pop / thump / whoosh (synthesized in code. No external audio sources or paid narration)
- BGM: [needed / not needed]. If needed, a chord progression [e.g. Am → F → C → G] and a style [calm / upbeat]. Align the music's peak with the bar of the visual peak (the hero's entrance). For detailed requests, use `music-brief.md` (references/music-brief.md)
- Mix: -14 LUFS ±1, true peak at or below -1 dBFS
</audio>

<process>
Brief → feasibility test for hard scenes → cut sheet (first/last frame + FB column) → self-review and fix the worst 3 → human FB → next version …… → **human OK** → final render
</process>

<delivery>
final.mp4 (per aspect) + poster.png + contact.png + source/ + README.md
</delivery>
```

## Asking questions to fill missing items

Do not ask everything at once. Ask only what is undecided, in this order (up to 3 questions at a time):

1. For whom, what, how many seconds, and where it will play (this decides the logline and aspect)
2. What assets are available (screenshots, recordings, logo, sources for numbers). **Do not create assets that do not exist**
3. Tone and reference videos (on the premise that only the grammar is carried over)
4. Is sound needed, is BGM needed (if so, the chord progression and calm / upbeat), BPM preference (120 if none)
