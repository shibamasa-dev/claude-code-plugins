# Notations drawn by hand in SVG

For the SVG/HTML output form (SKILL.md §4). The notation rules in SKILL.md §1–§3 hold unchanged; this file only says what each one looks like when drawn by hand. Colors, light and dark, accessibility and the legend come from one-page-diagram's `references/svg.md`: read it first and take every color from its variables.

## Shared conventions

- One `<style>` block, classes named per notation (`seq-head`, `st-state`, `fl-step`), every color a `var(--...)` from svg.md. No color value on an element. Prefix every class and `id` with the diagram's slug.
- Arrowheads: one `<marker>` per head style in `<defs>`. A filled triangle for calls, transitions and flow; an open chevron for replies. `fill="context-stroke"` (or `stroke="context-stroke"` for the chevron) lets a colored line keep a matching head.
- One meaning per line style, listed in the legend: solid = call or transition, dashed = reply, dotted = note link. A semantic color (a failure path in `var(--accent)`) is one class, used for every line it applies to.
- Draw order: frames and lanes, lifelines, edges, label patches, boxes, text (svg.md, Layout).

## Sequence

- Participants: a row of equal boxes across the top (about 150×44, centers 190 apart), name centered. A person may carry a person icon (one-page-diagram `references/icons.md`); a system does not.
- Lifelines: a dashed vertical line from the bottom of each box to the bottom of the figure.
- Messages: horizontal lines between lifelines, one per row, rows 36–40 apart, top to bottom in time order. The label sits centered above the line, 8 above it. A self-call is a short loop out to the right and back one row lower.
- Replies: dashed line with the open head, drawn only when the caller waits (SKILL.md §3).
- Activation: a narrow box (12 wide) on the lifeline from the call it receives to the reply it sends. Messages attach to the activation's edge, not the lifeline's center.
- `alt` / `opt` / `loop` frames: a rectangle across every lifeline the fragment touches, a pentagon tab with the keyword at its top left, the guard in brackets next to the tab, and a dashed divider between `alt` branches with the next guard under it. Start each guard to the right of the first lifeline it would cross, or put it on a label patch.
- Keep frame edges clear of messages: a frame starts a full row below the last message before it (a self-call loop included), and a message after the frame sits a full row below its bottom edge, outside it.
- Numbering the messages is optional; when the reply text walks through them, number them.

## State

- States: boxes with rounded corners (`rx` 10 or more), named as conditions.
- Start: a filled circle (radius 7) with one transition out, labelled with the creating event. End: a filled circle inside a ring.
- Transitions: arrows labelled with the event (`[guard] / action` after it when needed). The label sits beside the arrow's midpoint on a patch, never on the box.
- Self-transition: a loop leaving the top or right edge and coming back to the same edge, its label outside the loop.
- Lay states out on a grid in the main path's order (left to right, or top to bottom), with exceptions and terminal states off to one side.

## Flowchart and swimlane

- Steps: rectangles with a verb phrase. Decisions: a diamond holding a short question; every outgoing edge labelled (`yes` / `no`, or the values), the label right next to where the edge leaves the diamond. Start and end: a stadium shape (fully rounded ends).
- Main path straight down (procedure) or straight across (pipeline). Branches go to one side and rejoin below; a loop back runs along the outside edge.
- Swimlanes: one band per actor, the actor's name in a header strip at the band's start, steps inside their band. Bands alternate between `var(--bg)` and `var(--box)` fills, or are separated by a hairline. An edge crossing lanes is drawn straight across, never along a lane border.

## ER

- Entities: a box with the name in a header strip; attributes, when listed, one per line below a hairline, keys first and marked `PK` / `FK`.
- Relationships: lines between entity edges, orthogonal, with crow's-foot marks at each end: a bar for one, a circle for zero, a three-line fork for many. Both ends are always marked. The verb phrase sits at the middle of the line, on a patch.
- Put the entity most others refer to in the middle; keep lines from crossing boxes.

## Component and C4

- Boundaries are labelled containers (a thin rounded rectangle, name top left); the boxes inside are components or containers. C4 boxes carry name, type in brackets and the one-line description, smaller.
- Edges are labelled with what is sent (`writes order`), and with the protocol in C4.

## Layout

- Use a grid: positions, sizes and gaps on multiples of 4; equal spacing between peers (participants, states in a row, lanes).
- Leave at least 24 between a label and any box or line it does not belong to. Labels never cross a line or another label; when two would collide, move one row or widen the gap before shrinking text.
- Arrows never cross text. When a line has to cross a label area, route around it or put the label on a patch.
- Text sizes: 13–14 for box names and labels, 12 for guards and secondary text; never below 11.
- Size the `viewBox` to the content plus a margin of 16–24, and set no fixed width or height.

## Render and look

Same as one-page-diagram §7, in both themes: open the file in a browser or take a headless screenshot, once with a light and once with a dark color scheme. Check that every label fits, nothing overlaps or is clipped, the reading direction is obvious, line styles match the legend, and a colored line is visible on both backgrounds. Fix and render again, twice at most.
