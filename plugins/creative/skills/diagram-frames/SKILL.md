---
name: diagram-frames
description: Read before drawing a structural diagram as markup or code (Mermaid, SVG, HTML, draw.io, PlantUML, ASCII): architecture, system or component diagrams, flowcharts, sequence, swimlane or state diagrams. Declares in one line what a box stands for (components, process steps, actors or states), writes that in the caption or legend, checks every box against it, and splits the figure in two instead of mixing kinds. Use it for "draw an architecture diagram", "make a flowchart", "diagram this system", "the boxes in this diagram are inconsistent", or in Japanese 「構成図を描いて」「フロー図を作って」「図解して」「システム構成図」「業務フロー図」「状態遷移図」「図の枠がバラバラ」「図の粒度が揃っていない」. Not for generated images or illustrations (use image-generation-prompt) and not for data charts.
last_reviewed: 2026-11-17
review_after: 2027-05-16
---

# diagram-frames: decide what a box means before drawing

A diagram breaks when its boxes mean different kinds of things. A typical failure: an architecture diagram that puts processing steps (split, extract, verify), a place where data sits (an inbox folder) and a piece of software (a server) side by side in identical boxes. The cause is pouring items from the text straight into boxes without first deciding what a box means. Copying the look of a sample diagram does not help either: the sample worked because it kept one meaning per box, and that is the part that gets lost.

This skill only fixes the meaning of the boxes. Layout, styling and rendering are up to whatever skill or tool draws the diagram.

## Procedure

1. **Declare one axis before drawing.** Write one line: "a box in this diagram is a ___". Pick exactly one:
   - components (software, services, data stores)
   - process steps
   - actors (people, teams, systems acting)
   - states

   The diagram type and the axis go together: an architecture diagram uses components, a flowchart uses process steps, a swimlane or sequence diagram uses actors, a state diagram uses states. Never mix two axes in one figure.
2. **Put the declaration in the caption or legend** (`figcaption` in HTML, a title or note in Mermaid). Example: "Boxes are components (software and data stores). For the processing steps, see the flow diagram." It guides the reader and also fixes the standard you check against in the next step.
3. **Check every box after drawing.** Ask of each box, one at a time: "is this a ___?" (the declared axis). When a box fails, either (a) move it to the diagram where it belongs, or (b) change the axis and redo the check. Never ship a figure with mixed boxes.
4. **Split instead of cramming.** Wanting to show a processing flow inside an architecture diagram is the sign that a second diagram is needed. Make a pair (architecture + flow) rather than squeezing steps into component boxes.

Arrows and edges are not boxes: label them with what moves or happens between boxes (`writes`, `calls`, `on timeout`); they do not change the axis.
