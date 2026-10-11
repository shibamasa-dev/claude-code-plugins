# Music brief (MUSIC BRIEF) template

The order form for BGM. The human may write it; in the rough-notes entry point (`brief-template.md`), the agent proposes it first together with the cut breakdown, and the human corrects it.
Put it in the project folder as `music-brief.md`.

```markdown
# MUSIC BRIEF: [project name]

## Theme (in a few words)
[e.g. Starts quiet, opens up just once at the logo]

## Basics
- Use: [e.g. vertical video on X, for viewers watching with sound on]
- Length: [e.g. 15 seconds]
- Feel of the tempo / BPM: [e.g. relaxed, 120]
- Delivery format: [e.g. mixed into the mp4 (-14 LUFS)]

## Mood (0–10. 5 is the middle)
| Left | 0 ←→ 10 | Right |
|---|---|---|
| Quiet | [3] | Intense |
| Dark | [6] | Bright |
| Minimal | [4] | Rich |
| Organic | [5] | Digital |
| Serious | [4] | Playful |
| Nostalgic | [6] | Fresh |

## Sonic direction
- Genre: [e.g. ambient-leaning pop]
- Sounds to include: [e.g. piano, soft pads]
- Sounds to avoid: [e.g. brass, vocals]

## Structure and climax
| Section | Seconds | Contents |
|---|---|---|
| Intro | 0–3 | [pad only] |
| Development | 3–9.5 | [arpeggio comes in] |
| Climax | 9.5–12 | [thickest] |
| Tail | 12–15 | [hold the chord to the end] |

Pins: drop [—] / break [—] / high point [12.0s (logo lands)]

| Time | What happens on screen | What the sound should do |
|---|---|---|
| 0.0 | A surface rises | Attack on beat 1 |
| 12.0 | Logo lands | The music's peak. Thickest here |

## Reference tracks
[Track title — what you like about it (the pad opening up at 0:32–0:45)]. Do not copy the melody as-is.

## Picture of the video
[Cut sheet cutsheet.html version, and a one-line impression]

## Notes
```

## Mapping to `music.mjs`

Right now `scripts/music.mjs` composes BGM in a fixed arrangement template (it does not write a melody). Brief fields map only to the following parameters (how to write them: `authoring.md`, "9. Sound").

| Brief field | Maps to | How |
|---|---|---|
| Feel of the tempo / BPM | `meta.audio.bpm` | Use the number if given. "relaxed" ≒ 90–110 / "normal" ≒ 120 / "fast" ≒ 140+ |
| Mood: quiet ↔ intense | `music.style` | 5 or below → `calm`, 6 or above → `upbeat` (adds drums) |
| Mood: dark ↔ bright | `music.progression` | Dark → a minor progression (e.g. `Am, F, C, G`), bright → a major progression (e.g. `C, G, Am, F`). If the reference track's progression is known, use it |
| Mood: minimal ↔ rich | scene `energy` (0..1) | Minimal-leaning: low overall (0.3–0.5); rich-leaning: high (0.7–1.0). Changes which layers come in and out |
| Structure and climax (sections) | scene `energy` | Write energy per section (intro low, climax 1.0, tail slightly low) |
| Pins (high point, drop) | `meta.audio.peaks` | Put the high point's second in, snapped to a bar start. The music's peak (pad swell, crash) lands here |
| Events by time | `meta.audio.cues` | "Attack", "pop" etc. become sound effect cues (click / pop / thump / whoosh). Not BGM |
| Delivery format | no change | Always -14 LUFS ±1, true peak at or below -1 dBFS |
| (variation, another take) | `music.seed` / `music.humanize` | No field in the brief. When the human says "something different", change the seed |

**Fields not reflected right now** (fine to fill in, but they do not affect the BGM. Say so when showing it to the human):

- Mood: organic ↔ digital / serious ↔ playful / nostalgic ↔ fresh (timbre is fixed to the two styles)
- Sonic direction: genre, sounds to include, sounds to avoid (instruments are decided by style. There is no way to choose GM program numbers)
- The reference track's "what you like about it" (timbre and mix texture cannot be imitated. Only the progression carries over)
- Breaks (silent sections). BGM does not stop. For silence, split the video or do not add BGM
- Melody, vocals

If the unreflected fields are the heart of the brief, tell the human this skill's BGM cannot deliver it, and let the human decide whether to skip BGM or what to do instead (this skill does not use generative-AI composition).
