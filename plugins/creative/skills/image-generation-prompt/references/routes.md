# Calling each route

The route ids that `image_routes` and `video_routes` take. Whatever the route, the same three rules hold:

1. **Hand it the structured instructions** (the five-section structure in SKILL.md), not a free-form sentence of praise words.
2. **Name an absolute save path in the instructions or the call.** Otherwise the file may land only where the route keeps its own outputs, and you won't know where it is.
3. **Open the saved file yourself afterwards**: does it exist, what are its size and resolution, and does it look like what was asked. Don't report a result you haven't looked at.

Don't pin a model name in prompts or saved settings. Model names go stale; use the route's default, or look the current name up in the provider's documentation when the call needs one.

## `codex`: the Codex CLI's built-in image tool

Images only. Codex has an image-generation tool built in, so a plain-language request in `codex exec` generates the image and saves it as a file.

```bash
codex exec --skip-git-repo-check -s workspace-write -C <save folder> "<the five-section instructions>

Save the generated image as PNG to <absolute path>/out.png."
```

- `-s workspace-write` lets it write files; in a read-only sandbox it can't save. `-C` sets the folder it may write in, so make the save path sit inside it.
- Don't pass `-m`: leave the model to Codex's default.
- Cost depends on how Codex is signed in, so run `codex login status` before proposing. Signed in with a ChatGPT account, it counts against that plan's usage instead of a per-image charge. Signed in with an API key, it is billed per token on the API account. Either way one image uses a large share of tokens compared with a text task, so mention it when proposing several images.
- Needs: the Codex CLI installed and signed in (`codex login status`).

## `gemini`: the Gemini API

Images and video. Call the API directly with `GEMINI_API_KEY` from the environment (never paste the key into a command or a file).

- Write the returned image or video bytes to the absolute save path yourself; the API returns data, not a file.
- Video generation runs as a long operation: start it, poll until it is done, then download the result.
- Cost: billed per image or per second of video on the user's Google account. Check the provider's pricing page for current rates before stating a figure.

## `openai`: the OpenAI Image API

Images, including edits with a mask (inpaint). Call it with `OPENAI_API_KEY` from the environment.

- The response carries the image as base64 data or a URL; decode or download it to the absolute save path.
- Cost: billed per image, by size and quality. Check the provider's pricing page before stating a figure.

## `fal`: fal.ai

Many third-party image and video models behind one API. Use it when a model only fal offers is needed. Call it with `FAL_KEY` from the environment.

- The result is a URL; download it to the absolute save path before it expires.
- Cost: billed per call, and the price differs by model. Check the model's page on fal.ai.

## When no route fits

When none of the configured routes can do what the request needs (for example, an edit with a mask when only `codex` is configured), say so in the proposal and suggest the route that can, instead of quietly switching.
