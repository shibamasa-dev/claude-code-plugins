---
name: image-generation-prompt
description: Structures image-generation instructions, independent of the generation route (codex image2 / Gemini API / OpenAI Image API / fal.ai). Always use it right before generating an image, diagram, illustration, hero image, mockup, banner or icon, and turn the request into the five-section structure before handing it to the route. Also use it when redoing an image that missed the intent, when instructing an edit (inpaint / background swap), or when compositing several images. Triggers on "generate image", "edit this image", "make a diagram", "make an illustration", "make a mockup", or in Japanese 「画像生成」「図を作って」「イラスト作って」「モック作って」「この画像を編集して」.
last_reviewed: 2026-09-07
review_after: 2027-03-06
---

# Building image-generation prompts

**Structure the instructions here before choosing a route.** The route priority itself belongs to the user's rule file (the one that defines image-generation routes, if any). This skill only covers what to write and how.

The practices below were verified on GPT Image 2-generation models (codex image2, the OpenAI Image API, and the same model via fal.ai). The benefit of structure carries over to other families such as Gemini, but details (strength of text rendering, maximum number of reference images) differ by model.

## The five-section structure

```text
Scene: environment, light, time of day
Subject: the main subject (who/what, where, doing what)
Important details: materials, textures, lighting, camera angle, mood
Use case: magazine editorial photo / product mockup / UI screen / diagram, etc.
Constraints: no watermark, no logos, preserve the face, a single subject, etc.
```

**The fifth section is the easiest to drop and the most effective.** Hand over only ideas without boundaries and the model gets creative "in directions you will regret".

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
