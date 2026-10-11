# Installing the BGM soundfont and impulse responses, and their licenses

Only needed for videos that use BGM (`meta.audio.music`). Not needed for videos with sound effects only.
Do not put sound source files in the skill's repository; put them outside the skill (`~/.local/share/motion-video/`).

## FluidSynth

```bash
brew install fluid-synth        # verified with 2.6.1. LGPL-2.1
fluidsynth --version
```

render.mjs calls `fluidsynth` from PATH. If it is missing, storyboard / final for a video that specifies `music` stops with an error (it does not silently drop the BGM).

## Soundfont: GeneralUser GS (default)

| Item | Value |
|---|---|
| Version | GeneralUser GS v2.0.3 (License v2.0) |
| Author | S. Christian Collins (<https://www.schristiancollins.com/generaluser>) |
| Source | commit `684543d5e5efaef08d02be50dcda8d552478fa60` of <https://github.com/mrbumpy409/GeneralUser-GS> (the author's official repository) |
| Location | `~/.local/share/motion-video/soundfonts/GeneralUser-GS.sf2` (put the license text next to it as `GeneralUser-GS.LICENSE.txt`) |
| sha256 | `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe` (32,319,396 bytes) |

```bash
mkdir -p ~/.local/share/motion-video/soundfonts && cd ~/.local/share/motion-video/soundfonts
C=684543d5e5efaef08d02be50dcda8d552478fa60
curl -fL -o GeneralUser-GS.sf2 https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/$C/GeneralUser-GS.sf2
curl -fL -o GeneralUser-GS.LICENSE.txt https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/$C/documentation/LICENSE.txt
shasum -a 256 GeneralUser-GS.sf2   # must match the value above
```

License highlights (from `GeneralUser-GS.LICENSE.txt`):

- "You may use GeneralUser GS without restriction for your own music creation, private or commercial." — the music you make (= this video's BGM) can be used without restriction, privately or commercially
- About the included samples: "allow full use in music production, including the ability to make profit from musical recordings created with GeneralUser GS"
- However, the author also writes "I cannot be 100% sure where all of the samples originated" and cautions "This uncertainty may concern you if you intend to use GeneralUser GS in a commercial software product". This matters if you bundle the soundfont itself in a software product (audio rendered out as a video's BGM falls under the first point above)
- When distributing, do not link directly to the author's download file (link to the author's site, or host your own copy)

To switch to another sound source, pass it via `music.soundfont` (path relative to the project) or the env var `MOTION_VIDEO_SF2`. With a General MIDI compliant SF2, the styles' program numbers work as-is. Check its license before installing, and add it to this table.

## Impulse responses (convolution reverb)

- **Synthetic by default**: `synthIR` in `scripts/music.mjs` builds exponentially decaying stereo noise from a fixed-seed random generator (higher frequencies decay faster, approximating room absorption). No download or license needed, and the waveform is identical every time. Its length is `music.reverbSeconds` (default 1.6 seconds)
- **Using a measured IR**: pass a WAV via `music.ir` (path relative to the project). A suggested location is `~/.local/share/motion-video/ir/` or inside the project. Licenses differ per IR, so check before installing and add a table here (candidate: most IRs on OpenAIR <https://www.openair.hosted.york.ac.uk/> are CC BY-style and require attribution if used)

## On determinism (measured on 2026-10-01)

- FluidSynth 2.6.1's fast-render (`-F`) outputs the same sample sequence every time for the same MIDI and same SF2 (it matched even with internal reverb and chorus on, but the skill turns them off)
- However, the WAV that FluidSynth writes has the render time in the header's PEAK chunk, so **the file hash changes every time**. The sample data matches. The skill reads only the samples via ffmpeg, so the mp4 is unaffected
- When ffmpeg's `sidechaincompress` was fed two separate files, the output length changed from run to run depending on which ran out first at the end. The skill combines sound effects and BGM into a single 4ch WAV and then splits them for use
