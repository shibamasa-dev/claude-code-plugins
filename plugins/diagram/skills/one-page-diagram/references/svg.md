# SVG mechanics

## Light and dark in one file

Take every color from a CSS custom property, so one file carries both themes. Never write a color value on an element.

```html
<style>
  :root {
    --bg: #ffffff; --ink: #1f2328; --muted: #656d76;
    --line: #8c959f; --box: #f6f8fa; --accent: #0969da;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0d1117; --ink: #e6edf3; --muted: #8d96a0;
      --line: #6e7681; --box: #161b22; --accent: #4493f8;
    }
  }
  body { background: var(--bg); }
  svg text { fill: var(--ink); font-family: system-ui, sans-serif; }
  .box { fill: var(--box); stroke: var(--line); stroke-width: 1; }
  .edge { stroke: var(--muted); fill: none; }
  .focus { stroke: var(--accent); }
  .logo-dark { display: none; }
  @media (prefers-color-scheme: dark) {
    .logo-light { display: none; }
    .logo-dark { display: inline; }
  }
</style>
```

The values above are a neutral default. When the project has its own design tokens, or the host supplies theme variables, use those instead.

A host that sets the theme itself (an attribute on the root element, or its own variables) needs the same overrides under that selector as well as under the media query.

An SVG saved as a standalone `.svg` file can carry the same `<style>` block inside it. An SVG embedded in Markdown through an image tag follows the viewer's system theme, not the page's.

## Accessibility

```html
<svg role="img" aria-labelledby="d1-title d1-desc" viewBox="0 0 960 560">
  <title id="d1-title">Order flow from storefront to warehouse</title>
  <desc id="d1-desc">Boxes are applications; bands are the environments they run in.</desc>
</svg>
```

- `<title>` is short, about 60 characters. `<desc>` is one sentence, and the declaration of kinds is a good one.
- Prefix every `id` with a per-diagram slug, so two diagrams on one page do not collide.
- Text against its background needs a contrast ratio of at least 4.5:1, and arrows and box borders at least 3:1 against the page background, in both themes. The default tokens above meet both.

## Layout

- Set `viewBox` and let the width scale; do not fix pixel width and height on the `<svg>`.
- Draw in this order, so later layers sit on top: bands and containers, edges, edge-label patches, boxes, text.
- An edge label sits on a rectangle filled with `var(--bg)`, a few pixels larger than the text.
- Define arrowheads once in `<defs>` as a `<marker>` and reuse them. `fill="context-stroke"` makes the head follow the line color where the renderer supports it; otherwise define one marker per line color.
- Text does not wrap in SVG. Break long labels into `<tspan>` lines by hand, or shorten the label and move the wording to the legend. Budget about 0.6 em of width per Latin character and 1 em per full-width character (Japanese, Chinese, Korean), and break at a phrase boundary, never inside a word or a bracketed pair.
- For text in a script the system UI font may not cover, name fonts for it after `system-ui` in the `font-family` stack.

## Legend and caption

Put both inside the figure, so they travel with it when it is copied.

- Legend: one row per kind (swatch or icon, then the name), one per semantic style, and one line for what an arrow means.
- Caption: one sentence on what the diagram shows, and one on the viewpoint it leaves out ("Order of calls is not shown; see the sequence diagram").
