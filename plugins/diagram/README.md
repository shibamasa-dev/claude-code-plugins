# diagram

English | [日本語](README.ja.md)

Skills for drawing diagrams as code.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install diagram@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `one-page-diagram` | A one-page explanatory diagram as inline SVG or HTML: an architecture overview, an organization chart, a business concept. Tags every element with one kind (at most four per diagram), keeps only same-kind elements side by side, gives arrows one meaning, and says in the caption which viewpoint was left out. Uses official logos for named services and one concept icon per kind |
| `typed-diagram` | A diagram whose notation fixes what a box means: flowchart, swimlane, sequence, state, ER, component or C4. Mermaid for Markdown that lives in a repo; a hand-drawn SVG in HTML for proposals, client reports, slides and shared pages; PlantUML or draw.io when asked. Picks the type from the reader's question, checks every box against one declared meaning, and splits the figure instead of mixing kinds |

The two skills share one question to decide between them: does an existing notation already fix what a box and an arrow mean? If it does, `typed-diagram`; if not, `one-page-diagram`.

When a reply or document makes two or more points about the same SVG figure, both skills can step the reader through them on that one figure with `scripts/stepper/stepper.mjs`: Back and Next move the emphasis (a thicker outline on the current point's elements, the rest faded, an optional badge) while the layout and every color stay as drawn. The point list stays readable without JavaScript, and the skill writes every point in the reply text too. Where HTML cannot be shown, the points are numbered on one figure instead.

Both render the diagram and look at it before delivering, in light and dark, and say so when they could not.

## Configuration

The plugin has no settings and no hooks, and keeps nothing in its plugin data directory.

### Where files go

| What | Where |
|---|---|
| The diagram | the path you name. Otherwise inside or next to the document it illustrates, or `diagrams/<slug>.html` (`.mmd` for Mermaid) under the working directory. In a conversation it is shown inline |
| The stepper's spec, its HTML fragment and its light and dark preview pages | the session scratchpad. The fragment is then shown inline or put inside the diagram's HTML file |
| Downloaded icons and the files made to check the rendering | the session scratchpad, or the system temp directory when there is none |

## Limitations

- Logos and concept icons are downloaded while drawing (svgl, Devicon, gilbarbara/logos, Lucide), so that step needs network access. Without it the skill uses text labels and says so. The finished file embeds its icons and needs no network
- An SVG shown in Markdown through an image tag picks light or dark from the color scheme the embedding page declares, or from the system theme when it declares none. That can differ from the theme the page shows
- The stepper refuses a figure with a script element or an event attribute, and one that contains a `#` followed by three or more hex characters, because that reads as a color value. An id reference such as `url(#ab1-arrow)` matches too, so name ids so they do not look like colors
- Mermaid's C4 diagrams are experimental; on GitHub the skill draws a C4 level as a flowchart unless you ask for the C4 syntax

## Requirements

- A way to look at the result: a preview in your Claude client, or Chrome for a headless screenshot
- Node.js 20 or later for the stepper and the tests (tested with Node.js 24)
- Optional: Node.js, to render Mermaid with `@mermaid-js/mermaid-cli`

## Tests

```bash
bash plugins/diagram/tests/run-all.sh   # the stepper's checks and output; needs Node.js
```
