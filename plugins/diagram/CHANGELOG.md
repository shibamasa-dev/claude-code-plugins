# Changelog

Changes to the diagram plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.2.0] - 2026-11-24

### Added
- Stepper (`scripts/stepper/stepper.mjs`, used by both skills): walks the reader through two or more points on one SVG figure with Back / Next and a whole-figure view. It checks the spec first (title, an `<svg>`, no hex or `rgb()` color values, no script element or event attribute, two or more steps, focus ids present in the figure, a valid `here` and `mark`) and writes an HTML fragment plus light and dark preview pages. Emphasis is opacity and stroke width only, so every element keeps its color; the point list is readable without JavaScript. Ported from the MIT-licensed stepper in u-ichi/agent-plugins, with colors taken from `references/svg.md` instead of a widget host's variables
- `typed-diagram`: a hand-drawn SVG in HTML output for documents read as a finished piece (proposals, client reports, slides, shared pages), next to Mermaid for Markdown in a repo. `references/svg-notation.md` says how each notation looks in SVG and how to lay it out and check it
- `one-page-diagram` and `typed-diagram`: a section on several points on one figure, with the numbered fallback where HTML cannot be shown
- `references/svg.md`: `--pill`, `--badge` and `--badge-ink` in both themes
- Tests: `tests/run-all.sh` runs the stepper's `node --test` suite

## [0.1.0] - 2026-11-21

### Added
- `one-page-diagram` skill: draws a one-page explanatory diagram (architecture overview, organization, business concept) as inline SVG or HTML. Every element gets one kind from a set of at most four declared for the diagram, only same-kind elements sit side by side, arrows carry one declared meaning, and the caption says which viewpoint was left out. Named services get their official logo and kinds can carry a concept icon
- `typed-diagram` skill: draws a diagram whose notation already fixes what boxes and arrows mean (flowchart, swimlane, sequence, state, ER, component, C4), in Mermaid by default. It picks the type from the question the reader asks, keeps one meaning per box, and splits a figure instead of mixing kinds
- Both skills render the result and look at it before delivering, and say so when they could not
