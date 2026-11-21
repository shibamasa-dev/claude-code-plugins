# Icons

Two kinds of icon, with different rules. A logo identifies one named thing. A concept icon identifies a kind.

## Official logos

For an element that is a named service, product or platform.

1. Search before fetching, because file names do not always match the brand name:

   ```sh
   curl -s 'https://api.svgl.app?search=<name>'
   ```

   The result lists a `route` per match, either one URL or a `light` / `dark` pair, and sometimes a `wordmark`.
2. Sources, in order: [svgl](https://svgl.app/), then [Devicon](https://devicon.dev/), then the [gilbarbara/logos](https://github.com/gilbarbara/logos) collection, then the vendor's own site or official architecture icon package (cloud vendors publish one).
3. Inline the SVG into the delivered file so the diagram renders without network access.
4. Never recolor, redraw, crop, flip or stretch a logo. Scale it uniformly.
5. Dark backgrounds: use the vendor's official dark variant. Include both variants and switch them with the theme when the output form supports it (see [svg.md](svg.md)). Put the light variant on a light tile only when no dark variant exists and the logo would lose contrast.
6. No official logo found: use a plain text label. Do not draw a substitute.
7. The same logo more than once on a page: suffix the `id` values inside each copy (gradients, clip paths, masks) and the `url(#...)` references to them with a per-instance marker, or the copies collide. This renaming is bookkeeping, not a change to the artwork.

Fetching needs network access. When there is none, use text labels and say the logos are missing.

## Concept icons

For a kind, not for a named thing.

Use one when:

- the diagram has two or more kinds and the icon lets the reader tell them apart without reading the legend first (people, data stores, documents, devices, external systems), and
- the kind is something physical or familiar that an icon says faster than a word.

Skip it when:

- every box would get the same icon, so it distinguishes nothing,
- the kind is abstract enough that no icon is obvious (a policy, a capability). A label is clearer than a guess,
- it would decorate a single box.

Rules:

- One icon set per diagram, so stroke weight and corner style match. [Lucide](https://lucide.dev/) (ISC license) works well: 24 x 24, stroke only, `stroke="currentColor"`, so it follows the theme's text color.

  ```sh
  curl -sL 'https://unpkg.com/lucide-static@latest/icons/<name>.svg'
  ```

- One icon per kind, the same on every element of that kind, listed in the legend next to the kind's name. Do not vary it per element (a phone for one application, a globe for another): that turns the icon back into decoration.
- A box that shows an official logo does not also get its kind's icon. Its position and style still show the kind.
- Keep the label. An icon accompanies the text and never replaces it.
- Concept icons take the neutral text color. The accent color stays reserved for the focal elements.
- No emoji, and no icon that resembles a real product's logo.
