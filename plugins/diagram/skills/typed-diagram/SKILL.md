---
name: typed-diagram
description: 'Draws a diagram whose notation fixes what a box and an arrow mean: flowchart, swimlane, sequence, state, ER, component or C4. Mermaid for Markdown in a repo; polished hand-drawn SVG in HTML for proposals, client reports, slides and shared pages; PlantUML or draw.io when asked. Picks the type from the reader''s question, declares what a box stands for, checks every box against it, splits instead of mixing kinds, can step through several points on one SVG figure, and renders the result to check it. Use it for "flowchart in Mermaid", "sequence diagram", "state diagram", "ER diagram", "C4 diagram", "diagram this for the README", "a sequence diagram for the proposal", "draw it as SVG, not Mermaid", or in Japanese 「フロー図を作って」「業務フロー図」「シーケンス図」「状態遷移図」「ER図」「Mermaid で描いて」「README に図を入れて」「スイムレーン」「提案書用の図」「Mermaid じゃなくて綺麗な図で」「シーケンス図を SVG で」. For a one-page overview or concept diagram with free layout, logos and icons, use one-page-diagram. Not for generated images or data charts.'
last_reviewed: 2026-11-21
review_after: 2027-05-20
---

# typed-diagram: let the notation carry the meaning

A sequence diagram, a state diagram and an ER diagram each come with a rule for what a box and an arrow mean. The work is choosing the notation that matches the reader's question and then not bending it. The usual failure is bending it: processing steps drawn as components, actions drawn as states, a flowchart that is half architecture.

## Which skill

Ask one question: does an existing notation already fix what a box and an arrow mean here? If yes, stay here. If the reader wants how the whole thing fits together on one page, with several kinds of element, logos or free layout, use one-page-diagram.

## 1. Pick the type from the reader's question

| The reader asks | Type | A box is |
|---|---|---|
| What steps and decisions, in order | flowchart | a process step |
| Who does which step | flowchart with one subgraph per actor (swimlane) | a process step; lanes group steps by actor |
| Who calls whom, in what order | sequence | a participant (a person, service or system that sends or receives a message) |
| What states exist and what moves between them | state | a state |
| What entities exist and how they relate | ER | an entity |
| What the system is made of | flowchart used as a component diagram | a component (software, service, data store) |
| The architecture at one fixed level of detail | C4 (only when asked for C4 or a formal architecture document set) | a person, system, container or component, one level per diagram |

When two types fit, pick the one that answers the question the reader asked first, and offer the other as a second diagram.

## 2. Declare, draw, check

1. **Declare before drawing**, in one line: "a box in this diagram is a ___". The table above gives the answer for each type. Exactly one.
   Draw only what the request states. When it names no component, actor or state for something it describes (who escalates, where a job runs), do not invent one: leave it out and tell the user what is missing.
2. **Write the declaration in the title or a note** ("Boxes are components. For the processing steps, see the flow diagram."). It guides the reader and fixes the standard for the check.
3. **Check every box after drawing.** Ask of each one: "is this a ___?" When a box fails, move it to the diagram where it belongs, or turn it into an edge label. Never ship a figure with mixed boxes.
4. **Split instead of cramming.** Wanting to show the processing flow inside a component diagram, or the components inside a flow, is the sign that a second diagram is needed. Make the pair.

Edges are not boxes. Label them with what moves or happens between boxes, as an action or an event (`writes order`, `on timeout`), not a bare `uses`. Labels do not change what a box is.

## 3. Rules per type

- **Flowchart**: one start. Every decision has every outgoing edge labelled. Top-down for a procedure, left-to-right for a pipeline. Name steps as verb phrases.
- **Swimlane**: one subgraph per actor, steps inside. An actor never appears as a box.
- **Sequence**: a data store or queue is a participant only when the diagram is about the calls to it; otherwise leave it out. Show the reply when the caller waits for it. When the diagram documents a protocol or an integration, include the main failure path (timeout, rejection, retry) with `alt` or `opt`, because that is where readers get it wrong.
- **State**: name states as conditions the thing can be in (`Paid`, `Awaiting review`), never as actions. Label every transition with the event that causes it. Every state is reachable and either has a way out or is final. The event that creates the thing ("submitted") is the transition out of the start marker, not a state. A retry that leaves the state unchanged is a self-transition.
- **ER**: entities are nouns in the singular. Put the cardinality on every relationship and a verb phrase on its label. List attributes only when the diagram is the schema reference; otherwise names are enough.
- **Component**: boxes are things that exist at runtime or at rest (services, stores, queues), grouped by subgraph for the boundary they sit in. Steps go on edge labels or in a separate flowchart. People are not components: what a component sends to a person goes in a note under the diagram.
- **C4**: one level per diagram. Every element has a name, a type and a one-line description; containers and components name their technology.

Keep one diagram to about 12 boxes. Beyond that, split by boundary or by phase and link the parts from the caption.

## 4. Output: the form follows the destination

| Where the diagram goes | Form |
|---|---|
| A Markdown file that lives in a repo and is versioned (README, design doc, ADR) | Mermaid in a fenced `mermaid` block: it renders on GitHub and many Markdown viewers, and it diffs |
| A document read as a finished piece (proposal, client report, slides, a shared page or artifact) | Hand-written SVG in HTML |
| The user asks for PlantUML or draw.io, or the document set already uses one | That format |

When the user names a form ("as SVG", "in Mermaid"), that form wins over the table, whatever the destination. Sections 1–3 hold for every form: the same type choice, the same one-line declaration and the same box check. Only the drawing changes.

**Mermaid.** [references/mermaid.md](references/mermaid.md) has the syntax per type and the mistakes that break rendering. Read it before writing Mermaid. The diagram goes inside the document it illustrates; a standalone file goes to the path the user names, otherwise to `diagrams/<slug>.mmd` under the working directory.

**SVG in HTML.** Draw the notation by hand to the rules in §1–§3. [references/svg-notation.md](references/svg-notation.md) says how each notation looks in SVG (lifelines, activations, `alt` frames, state markers, decision diamonds, lanes, cardinality marks) and how to lay it out. Colors, light and dark, accessibility attributes, legend and caption follow one-page-diagram's [references/svg.md](../one-page-diagram/references/svg.md); read it first and take every color from its variables. Put the declaration from §2 in the caption or `<desc>`. Output places: inline in a host that renders HTML (an artifact, a widget, a preview pane); otherwise one self-contained HTML file at the path the user names, next to the document it illustrates, or `diagrams/<slug>.html` under the working directory.

Files made only to check the rendering go to the session scratchpad (the system temp directory when there is none).

### Several points on one figure (SVG only)

When the reply or the document walks through two or more points on the same figure (a sequence read call by call, a state diagram with two transitions that are wrong, a flow with two decisions to review), step through them on one figure instead of drawing one figure per point. The layout and every color stay; only emphasis moves. With one point, or when each point needs different elements drawn, draw separate figures.

Build it with the plugin's stepper:

1. Tag the SVG: `data-box="<id>"` on the `<g>` of each box, participant, state or frame a point can focus; `data-arrow="<id>"` on the `<g>` that holds a line together with its label. Lifelines, activations and the legend can stay untagged; they are never dimmed. The SVG holds no color values: take colors from classes that use the svg.md variables (the stepper output carries their values for light and dark). No `#` followed by three or more hex characters anywhere, including `url(#...)` references: name ids like `seq-ah`, not `ab1-arrow`.
2. Write the spec as JSON in the session scratchpad: `title`; `svg` (the markup) or `svgFile` (a path relative to the spec); optional `lead`, `source` (`{label, text}`: the request the figure answers) and `labels` (`{back, next, all}` in the reader's language); `steps`, each `{name, focus: [ids], here: <box id>, mark: <badge text>, point: <one-line conclusion>}`. `here` must be a box in `focus`; `mark` needs `here`.
3. Run it:

   ```sh
   node "${CLAUDE_PLUGIN_ROOT}/scripts/stepper/stepper.mjs" "<scratchpad>/steps.json" --out "<scratchpad>/steps.html" --preview "<scratchpad>/steps-preview"
   ```

   Replace `<scratchpad>` with the session scratchpad's absolute path. It refuses a spec with no title, an SVG that does not start with `<svg`, a hex or `rgb()` color value in the SVG (named colors such as `white` are not caught, so keep to the variables), a script element or event attribute, fewer than two steps, a focus id not in the SVG, or a bad `here` or `mark`, and prints why.
4. Use the fragment (`--out`, or stdout): pass it to the host's HTML widget, or put it inside the deliverable HTML file. `--preview` writes `light.html` and `dark.html` around it; look at every step and the whole figure in both (§5).
5. Write every point in the reply text as well, as the script's last line prints them: previews, notifications and summaries do not show the figure, and a reader who never clicks Next misses the later points. Without the script the point list is still readable.

For Mermaid, or wherever HTML cannot be shown, number the points on the one figure instead (number the messages or edges they concern, or add a note per point) and list one conclusion per number under it.

## 5. Validate before delivering

1. Run the box check from step 2 on the final text.
2. **Render it.** For SVG in HTML, open it the way the reader will and look at it in both themes, as references/svg-notation.md (Render and look) says; with the stepper, open both preview pages and look at every step and the whole figure. For Mermaid, syntax that looks right often fails to parse. Use what is available: the host's Markdown or Mermaid preview, or the Mermaid CLI when Node.js is installed:

   ```sh
   npx -y @mermaid-js/mermaid-cli -i diagram.mmd -o "${TMPDIR:-/tmp}/diagram-check.svg"
   ```

   The CLI needs network access on first use and a headless Chrome. When it reports a missing browser, install the one the error message names, or pass a Puppeteer config (`-p`) whose `executablePath` points at an installed Chrome.

   Without the CLI, a browser tool can load Mermaid from a CDN and call `mermaid.render` on each block. That proves the block parses.
3. Look at the result: no label cut off, no edge label on top of another, the reading direction obvious. Fix and render again, twice at most.

Report what you did: "rendered and looked at", "parsed, not looked at" or "not rendered". Do not present a diagram as checked beyond that.
