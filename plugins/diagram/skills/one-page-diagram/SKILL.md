---
name: one-page-diagram
description: 'Draws a one-page explanatory diagram as inline SVG or HTML: an architecture overview, an organization chart, a business concept or a "how it all fits together" picture, where no notation decides what a box means. Tags every element with one kind before drawing, keeps only same-kind elements side by side, gives arrows one declared meaning, uses official logos for named services and concept icons for kinds, and renders the result to check it. Use it for "draw a diagram of this", "explain this in one picture", "overview diagram", "concept diagram", "the boxes in this diagram are inconsistent", or in Japanese 「図解して」「一枚図にして」「全体像を図にして」「概念図」「構成図を描いて」「組織図」「ポンチ絵」「図の枠がバラバラ」「図の粒度が揃っていない」. For a sequence, state, ER or step-by-step flow diagram, or anything asked for in Mermaid or as C4, use typed-diagram. Not for generated images or illustrations, and not for data charts.'
last_reviewed: 2026-11-21
review_after: 2027-05-20
---

# one-page-diagram: one picture a first-time reader takes in at once

A one-page diagram goes wrong when its boxes mean different kinds of things: an application, the environment it runs in and a processing step all drawn as identical siblings. No notation prevents this, so each diagram declares its own kinds and is checked against them. The procedure below is the part that must be followed; the numbers in "Shape and style" are starting points.

## Which skill

Ask one question: does an existing notation already fix what a box and an arrow mean here?

| The reader asks | Skill |
|---|---|
| Who calls whom, in what order | typed-diagram (sequence) |
| What states exist and what moves between them | typed-diagram (state) |
| What steps and decisions, in order | typed-diagram (flowchart) |
| Who does which step of a process, in order | typed-diagram (swimlane) |
| What entities and how they relate | typed-diagram (ER) |
| A formal architecture document set, or C4 by name | typed-diagram |
| Who the parties are, what each is responsible for and what they use | this skill |
| How the whole thing fits together, on one page | this skill |

A software subject does not by itself mean typed-diagram or C4: a one-page explainer of a software system follows this skill's rules. Switch to C4 only when the user asks for C4 or the deliverable is a formal architecture document set.

When the user asks for Mermaid, use typed-diagram: Mermaid cannot nest, band and place freely the way this skill needs.

## 1. Decide whether a diagram earns its place

- Draw one only when the structure, flow or relationship is the point. When a short list, a table or two sentences say the same thing, write that instead and say so.
- A before/after comparison is a table. A single box is not a diagram.
- When a draft feels crowded, delete elements before adding decoration. Aim for a density a first-time reader takes in in one pass.

## 2. Decompose before drawing

Write this down before placing anything (in your working notes, not in the deliverable):

1. **List every element** the diagram needs, in the user's own terms.
2. **Declare the kinds**: at most four for this diagram, for example actor, activity, artifact and place, or application, data store and environment. Tag each element with exactly one. Drop an element that fits no kind instead of forcing it in. A container or band that only shows where other elements sit (an environment, a team, a boundary) is not a box: it gets a label, no kind tag, and does not count toward the four.
3. **Declare the diagram type**, exactly one of structure, flow or relationship. Mixed content gets a primary type; the rest is demoted to labels, numbers or the caption.
4. **Declare one meaning for arrows**, phrased as what travels along the arrow ("a request", "money", "reports to"). The arrow points the way that thing travels; who initiates (push or pull) is not drawn. Containment is nesting and sequence is numbers, not more arrow types. When two relations compete, the weaker one becomes labels or numbers.
5. **State the planned cuts**: what you are leaving out to keep the page readable. More than about 9 boxes or 12 arrows is usually two diagrams; elements that always travel together are one box. Containers, bands and the legend do not count.
6. **Do not fill gaps with guesses.** When the request does not say where something runs or who owns it, leave that out and say so in the caption, or ask. When the unknown sits on an element the diagram needs, write "unconfirmed" (in the diagram's language) on that element instead of a guess.

## 3. Keep kinds from mixing

- A row, group or layer that presents a set holds elements of one kind only.
- A chain in a flow may alternate kinds from step to step, because a chain shows a path, not a set. Tag every step so the alternation stays readable.
- An element of a different kind does not get a sibling box. It goes into a containing box (an application inside its environment), a separate band (a row of actors above the systems), or an arrow label (a processing step on the arrow between two components).
- A sequence demoted from a structure diagram becomes numbers: number the arrows in order, put a numbered badge on a box for a step that happens inside it, and list the step names once in the legend. More than about eight numbered steps means the sequence is the point: draw it as a flow with typed-diagram and keep this page for the structure.
- A second relation that is not a sequence (which team uses which system) becomes position: put the used thing directly under or inside the element that uses it, and say in the legend what the alignment means. Do not add a second kind of arrow for it.
- State in the caption which viewpoint the diagram leaves out, such as sequence, placement or timing.

## 4. Shape and style

- Let the shape mirror the concept: a fan-out for one-to-many, a line for sequence, convergence for aggregation. Avoid a uniform grid of identical cards. Test: with all text removed, the structure should still say something.
- Reserve one accent color for the one or two elements the reader should look at first. Everything else is neutral.
- A kind that carries meaning (success, error, decision, external) gets one style, defined once in the legend and used every time.
- In a technical diagram that would otherwise stay abstract, show one concrete example: a real payload, value or name.
- Starting points for SVG: box positions, sizes and gaps on multiples of 4 (text baselines, label lengths and the inside of an unmodified logo are off that grid); hairline borders, no shadows; gaps narrower than about 80 px carry only a step number or one short word, with the full wording in the legend. Widen a gap before shrinking a font.
- Arrows: orthogonal or straight, never across a label and never behind a box they do not connect to. A label on an arrow sits on an opaque patch of the background color. Two arrows on the same box edge get separate attach points.

[references/svg.md](references/svg.md) has the SVG mechanics: theme variables for light and dark in one file, the accessibility attributes and the legend.

## 5. Icons

- **Named services, products and platforms get their official logo**, unmodified. Never recolor, redraw or stretch one, and never invent a look-alike; with no official logo, use a text label.
- **A kind can carry a concept icon** (a person for actors, a cylinder for data stores, a document for artifacts) from one icon set. Use it when it lets the reader tell kinds apart at a glance, give every element of that kind the same icon, and list it in the legend. A box that already shows a logo does not also get the concept icon. An icon that only decorates one box, or an emoji, stays out.

[references/icons.md](references/icons.md) has the sources, the search step, dark-mode variants and how to inline them.

## 6. Output form

- A host that renders HTML inline (an artifact, a widget, a preview pane): inline SVG in HTML.
- A file to share or publish: one self-contained HTML file, light and dark in the same file, no network needed to render. Write it to the path the user names; otherwise next to the document it illustrates, or to `diagrams/<slug>.html` under the working directory when there is no such document.
- A Markdown document the user will version: a fenced Mermaid block through typed-diagram, or the SVG saved next to the document and referenced as an image.
- A diagram the user will keep editing by hand: offer an editable format such as Excalidraw or draw.io.

Downloaded icons, screenshots and any generator script are working files: keep them in the session scratchpad (the system temp directory when there is none), not next to the deliverable.

## 7. Validate before delivering

1. **Same-kind check**: for every row, group and layer that presents a set, read out the tags. All the same, or fix it.
2. **Legend check**: the legend lists every kind, every semantic style, every concept icon and the arrow meaning. Nothing appears in the diagram that the legend does not explain.
3. **Render and look**: open the result the way the reader will (the host's preview, a browser, or a headless screenshot such as `chrome --headless --screenshot="$TMPDIR/diagram-check.png" --window-size=1600,1000 file.html`) and look at it in both themes. When headless Chrome cannot start (a sandboxed shell often blocks it), serve the folder on localhost and open it with the host's browser tool. Check that every label fits its box, no arrow crosses text, nothing is clipped, and every icon is visible on its background.
4. Fix what you find and render again, twice at most. Then deliver, and name any defect that remains.

When you could not render it, say "not visually checked" in the reply. Do not describe the diagram's look as verified.
