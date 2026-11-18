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

## Requirements

- `motion-video`: Node.js, Chrome, ffmpeg
