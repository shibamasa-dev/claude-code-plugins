---
name: image-generation-prompt
description: Structures image-generation instructions, independent of the generation route (codex image2 / Gemini API / OpenAI Image API / fal.ai). Always use it right before generating an image, diagram, illustration, hero image, mockup, banner or icon, and turn the request into the five-section structure before handing it to the route. Also use it while building a page, app, deck, document or article where an image asset (hero image, icon, illustration, diagram, mock photo) would raise quality, to propose assets before anything is generated, and when redoing an image that missed the intent, when instructing an edit (inpaint / background swap), or when compositing several images. Keeps an image history (earlier attempts and reference images) so requests like "like the last one" reuse what worked. Triggers on "generate image", "edit this image", "make a diagram", "make an illustration", "make a mockup", or in Japanese 「画像生成」「図を作って」「イラスト作って」「モック作って」「この画像を編集して」「前の画像みたいに」「このテイストで」.
last_reviewed: 2026-11-23
review_after: 2027-05-23
---

# Building image-generation prompts

This skill covers when to propose images, what to write in the instructions, and which route to hand them to. Route call details are in [references/routes.md](references/routes.md).

The practices below were verified on GPT Image 2-generation models (codex image2, the OpenAI Image API, and the same model via fal.ai). The benefit of structure carries over to other families such as Gemini, but details (strength of text rendering, maximum number of reference images) differ by model.

## Before generating: propose, then wait for approval

1. **Propose assets without being asked.** While building a page, app, deck, document or article, when an image asset (hero image, icon, illustration, diagram, mock photo) would raise its quality, propose it instead of silently falling back to CSS, SVG or emoji. Each proposal gives:
   - how many images, and where each one goes
   - the style (one line, or the shared style template below)
   - the route you will use (see Routes)
   - a rough cost: whether the route bills per image or counts against a plan the user already pays for, and roughly how much

   Generating is not always the answer: small icons and simple shapes are often better as SVG or CSS. Say so when that is the case.
2. **Generate only after the user approves.** A generation call spends quota or money and produces something that cannot be taken back. Before approval, you may search the image history and design the prompt and the style template, nothing more. Making a reference proxy and recording an attempt come with or after the generation the user approved.
3. **Match earlier assets.** When the deliverable already has images, or the new image joins a series, look at the existing ones first and match their background, palette, line weight and typeface.

## Routes

Configured route order: images `${user_config.image_routes}`, video `${user_config.video_routes}`. Each is a comma-separated list of route ids (`codex`, `gemini`, `openai`, `fal`), tried in order. A value that still reads as a `${user_config...}` placeholder counts as empty. The video order applies when the user asks for a generated video clip; a video drawn in code with `motion-video` uses no route.

- **Empty**: ask the user which route to use, then offer to save their answer under the key for that medium only (`image_routes` for images, `video_routes` for video): `echo '{"<key>":"<their route ids>"}' | claude plugin configure <plugin id> --values-stdin`. The command changes only the keys it is given. The plugin id is the one from `claude plugin list`; run `/reload-plugins` after saving.
- **Set**: use the first route that is available and can do the job. When you skip a route (it is not installed, or it cannot edit or inpaint as the request needs), say which and why in the proposal.

How to call each route, and how to check what it saved: [references/routes.md](references/routes.md). **After every generation, open the saved file yourself** (size, resolution, a look at it). A route's "done" message is not proof.

## Image history: search before generating, record every attempt

Earlier attempts and reference images are kept in a database so later requests can reuse what worked. SQL forms, the route choice and reference roles: [references/history.md](references/history.md).

Saved settings: route = `${user_config.route}`, connector = `${user_config.connector_id}`, project = `${user_config.connector_project_id}`. A value that still reads as a `${user_config...}` placeholder counts as empty. The schema files are in `${CLAUDE_PLUGIN_ROOT}/migrations/`.

1. **Search the history first**, even for a request that sounds simple, with the request's key words. Say briefly what you found: a close earlier attempt to build on (and which part: composition, style, palette, typography, subject), or that nothing similar exists. When the user points at an earlier result ("like the last one", 「前の」「あの」「同じ感じ」), use the matching attempt unless there are several candidates.
2. **Give every reference image a role** (`composition_only`, `style_only`, …) before using or storing it, and keep a reusable one as a compact proxy:

   ```bash
   CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' uv run --quiet --script "${CLAUDE_PLUGIN_ROOT}/skills/image-generation-prompt/scripts/history.py" proxy "<image path>"
   ```

   Treat a reference as structure to learn from, not permission to copy: replace real logos, copyrighted characters, exact costumes and title copy unless the user owns them and asks for a faithful edit.
3. **Record every attempt** after generating, whatever the route: accepted results, rejected drafts, variants, edits, and a plan when generation is blocked. A refinement is a new row that points at the attempt it builds on; never overwrite history.

The history needs [uv](https://docs.astral.sh/uv/): it starts the `history` server and runs the proxy command. When the history tools are missing or the proxy command fails because uv isn't installed, tell the user once, then go on with the image work without the history. Don't keep the history anywhere else instead.

## The five-section structure

```text
Scene: environment, light, time of day
Subject: the main subject (who/what, where, doing what)
Important details: materials, textures, lighting, camera angle, mood
Use case: magazine editorial photo / product mockup / UI screen / diagram, etc.
Constraints: no watermark, no logos, preserve the face, a single subject, etc.
```

**The fifth section is the easiest to drop and the most effective. Never leave Constraints empty.** Hand over only ideas without boundaries and the model gets creative "in directions you will regret".

## Six principles

1. **Write visual facts, not praise.**
   "stunning / masterpiece / 8K / award-winning" → "overcast light, brushed aluminum, soft bounce light, 50mm equivalent"

2. **Give style words a visual landing point.**
   "minimal brutalist" → "cream background, heavy black sans-serif, asymmetric text blocks, generous whitespace"

3. **Name the thing itself.**
   Use concrete nouns such as "ticket gate", "boarding pass", "preserve the face" instead of mood words.

4. **In edits, separate "change" from "preserve".**

5. **Treat text as typography.**
   Wrap literals in quotes or ALL CAPS, and specify typeface, size, color and placement.

6. **One revision per turn.** Small iterations beat big rewrites.

## Three modes

### Generate

Use the five-section structure as is. Concrete patterns per use case are in [references/patterns.md](references/patterns.md).

### Edit (inpaint, background swap, weather change, clothing change)

```text
Change: exactly what to change, and nothing else
Preserve: face, identity, pose, lighting, framing, background
Constraints: do not add extra objects, no watermark
```

Add one more sentence about **physical consistency**: matching lighting, contact shadows, consistent perspective.

### Compositing several images

Give each input a role label and refer to the labels from the instructions.

```text
Image 1: base scene to preserve.
Image 2: jacket reference.
Instruction: dress the person in Image 1 in the jacket from Image 2.
Preserve the face, body shape, pose, background and lighting from Image 1.
```

Up to 16 reference images (GPT Image 2 family). **Always give every one of them a role.**

## Text inside images

The biggest strength of this model family. How to keep it intact:

- Wrap the exact text in quotes — `the sign reads "GRAND OPENING"`
- Or mark the literal with ALL CAPS — `text on the cup: HELLO WORLD`
- Specify the typeface — `bold serif`, `condensed sans-serif`, `handwritten`
- Specify the placement — `centered in the top third`, `bottom-left corner`
- Put `no extra words` and `no duplicated text` in Constraints
- If it still breaks, spell it letter by letter — `"X-R-A-Y"`

## Weak vs. strong

**Weak:**
```text
A stunning ultra-detailed cinematic masterpiece of a woman in a museum,
beautiful, photoreal, 8K, award-winning.
```

**Strong:**
```text
Scene: a museum gallery, late afternoon, soft overhead spotlights.
Subject: a woman in her 30s in a charcoal wool coat stands 3 meters away
  from a marble bust, glancing at the piece sideways.
Important details: 50mm equivalent, shallow depth of field, neutral cream walls,
  warm tungsten on the bust, cool ambient light on her face.
Use case: magazine editorial photo.
Constraints: no watermark, no logos, no heavy retouching, focus on a single subject.
```

## Putting several images into one deliverable

**Share a style template.** Fix the background, palette, line weight and typeface in one template sentence and reuse it for every image. Change only one axis per image.

Save generated images in the deliverable's own folder (for example `assets/`), and give the user a clickable relative link to each. A page that blocks images from other hosts (a claude.ai Artifact, for one) needs the images published with the page.
