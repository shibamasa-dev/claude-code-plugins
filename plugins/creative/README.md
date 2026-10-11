# creative

English | [日本語](README.ja.md)

Skills and hooks for making images, videos and designs.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install creative@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `image-generation-prompt` | Structures prompts for image generation. Independent of the generator (Gemini API, OpenAI Image API, fal.ai, …) |
| `motion-video` | Draws motion-graphics videos in code and renders them, with your product images, screenshots, logos or live-action clips |

## Hooks

| Hook | When | What it does |
|---|---|---|
| design-lint | After Edit or Write | When `DESIGN.md` is edited, runs `npx @google/design.md lint` and returns the findings. Does nothing for other files |

## Requirements

- `motion-video`: Node.js, Chrome, ffmpeg
- `design-lint`: `npx` (needs network access)
