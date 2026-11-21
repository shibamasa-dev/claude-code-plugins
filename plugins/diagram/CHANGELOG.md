# Changelog

Changes to the diagram plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.1.0] - 2026-11-21

### Added
- `one-page-diagram` skill: draws a one-page explanatory diagram (architecture overview, organization, business concept) as inline SVG or HTML. Every element gets one kind from a set of at most four declared for the diagram, only same-kind elements sit side by side, arrows carry one declared meaning, and the caption says which viewpoint was left out. Named services get their official logo and kinds can carry a concept icon
- `typed-diagram` skill: draws a diagram whose notation already fixes what boxes and arrows mean (flowchart, swimlane, sequence, state, ER, component, C4), in Mermaid by default. It picks the type from the question the reader asks, keeps one meaning per box, and splits a figure instead of mixing kinds
- Both skills render the result and look at it before delivering, and say so when they could not
