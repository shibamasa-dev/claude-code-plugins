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
| `typed-diagram` | A diagram whose notation fixes what a box means: flowchart, swimlane, sequence, state, ER, component or C4, in Mermaid by default. Picks the type from the reader's question, checks every box against one declared meaning, and splits the figure instead of mixing kinds |

The two skills share one question to decide between them: does an existing notation already fix what a box and an arrow mean? If it does, `typed-diagram`; if not, `one-page-diagram`.

Both render the diagram and look at it before delivering, and say so when they could not.

## Configuration

The plugin has no settings and no hooks, and keeps nothing in its plugin data directory.

### Where files go

| What | Where |
|---|---|
| The diagram | the path you name. Otherwise inside or next to the document it illustrates, or `diagrams/<slug>.html` (`.mmd` for Mermaid) under the working directory. In a conversation it is shown inline |
| Downloaded icons and the files made to check the rendering | the session scratchpad, or the system temp directory when there is none |

## Limitations

- Logos and concept icons are downloaded while drawing (svgl, Devicon, gilbarbara/logos, Lucide), so that step needs network access. Without it the skill uses text labels and says so. The finished file embeds its icons and needs no network
- An SVG shown in Markdown through an image tag picks light or dark from the color scheme the embedding page declares, or from the system theme when it declares none. That can differ from the theme the page shows
- Mermaid's C4 diagrams are experimental; on GitHub the skill draws a C4 level as a flowchart unless you ask for the C4 syntax

## Requirements

- A way to look at the result: a preview in your Claude client, or Chrome for a headless screenshot
- Optional: Node.js, to render Mermaid with `@mermaid-js/mermaid-cli`
