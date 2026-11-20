# creative

English | [日本語](README.ja.md)

Skills for making images and videos.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install creative@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `image-generation-prompt` | Structures prompts for image generation. Independent of the generator (Gemini API, OpenAI Image API, fal.ai, …) |
| `diagram-frames` | Read before drawing an architecture, flow, sequence or state diagram in Mermaid, SVG, HTML and the like. Fixes what a box means (one kind per figure) and checks every box against it |
| `motion-video` | Draws motion-graphics videos in code and renders them, with your product images, screenshots, logos or live-action clips |

`DESIGN.md` linting moved to the `lint` plugin. To keep it, run `/plugin install lint@shibamasa-plugins`.

## Configuration

### Where files go

| What | Where |
|---|---|
| A motion-video project (`brief.md`, `music-brief.md`, `verify.md`, `video.js`, `out/`) | the folder you name, else `motion-video/<slug>/` under the working directory |
| motion-video's working PNG sequence and audio files | `os.tmpdir()/motion-video/`, not removed automatically; delete it when the video is done |
| The soundfont for BGM | `~/.local/share/motion-video/soundfonts/`, where you put it |

It keeps nothing in its plugin data directory, so uninstalling removes none of these files.

## Requirements

- `motion-video`: Node.js, Chrome, ffmpeg
