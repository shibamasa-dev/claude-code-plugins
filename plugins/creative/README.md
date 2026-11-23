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
| `image-generation-prompt` | Proposes image assets when they would improve a page, deck or document, generates only after you approve, and structures the prompt for the route you configured (Codex, Gemini API, OpenAI Image API, fal.ai) |
| `motion-video` | Draws motion-graphics videos in code and renders them, with your product images, screenshots, logos or live-action clips |

`DESIGN.md` linting moved to the `lint` plugin. To keep it, run `/plugin install lint@shibamasa-plugins`.

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `image_routes` | empty | Route ids to try for images, comma-separated, first one first: `codex`, `gemini`, `openai`, `fal` (for example `codex,gemini`). Empty means Claude asks you, and offers to save your answer |
| `video_routes` | empty | Route ids to try for video, the same way: `gemini`, `fal` |

Set them in `/plugin`, or with `echo '{"image_routes":"codex,gemini"}' | claude plugin configure creative@shibamasa-plugins --values-stdin`, then run `/reload-plugins`. How each route is called is in `skills/image-generation-prompt/references/routes.md`.

### Where files go

| What | Where |
|---|---|
| A motion-video project (`brief.md`, `music-brief.md`, `verify.md`, `video.js`, `out/`) | the folder you name, else `motion-video/<slug>/` under the working directory |
| motion-video's working PNG sequence and audio files | `os.tmpdir()/motion-video/`, not removed automatically; delete it when the video is done |
| Generated images | the deliverable's own folder (for example `assets/`), with an absolute save path given to the route |
| The soundfont for BGM | `~/.local/share/motion-video/soundfonts/`, where you put it |

It keeps nothing in its plugin data directory, so uninstalling removes none of these files.

## Requirements

- `image-generation-prompt`: the route you use: the Codex CLI signed in (`codex`), or an API key in the environment (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `FAL_KEY`)
- `motion-video`: Node.js, Chrome, ffmpeg
