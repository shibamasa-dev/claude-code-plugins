# Board design

The rules behind [../assets/board.html](../assets/board.html). They were chosen by comparing four layouts and three looks on the same rows.

## Layout

- **Title, then the list.** No lead paragraph, no bulk actions ("fill the undecided with the recommendation"), no separate "excluded items" section. The only header extra is the decided count.
- **One row per item, split in two.** Left: number, name, kind, one-sentence description, evidence lines. Right: one box holding **every** input for that row, the decision fields and then the memo. Rejected alternatives: choices in table columns with the memo elsewhere (inputs scattered across the row), a side panel (the item and its inputs drift apart), rows that expand to show inputs (decisions hidden behind a click).
- **Options are radio lists, not dropdowns,** so every option and its recommended badge are visible without opening anything. The recommended option carries a badge (推奨 in Japanese); a one-line reason may sit under an option.
- Groups are headings above the rows, in the order the board defines.
- At phone width the input box moves under the description.

## Look

- Black and white plus one blue accent; the blue marks only what is chosen, the recommendation badge and focus.
- Square corners. Separation by rules, not fills: a 2px rule above each group's list, a 1px rule between rows, a 2px rule on the left of the input box.
- BIZ UDPGothic for text, IBM Plex Mono for names and numbers.
- A dark theme with the same structure (near-black ground, light-blue accent).
