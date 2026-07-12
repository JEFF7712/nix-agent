# nix-agent identity pass

Differentiate the landing page from the stock Nix logo without redrawing the
flake. Skin and behavior only: the snowflake silhouette and its `+*#=:@%&` glyph
substance are unchanged and stay Nix-blue. A single amber accent marks the
"agent" surfaces.

## Decisions

- Palette: blue `#5fb8f2` base + amber `#f2b25c` accent, pure-black background.
- Wordmark: terminal prompt `❯ nix-agent ▊` (amber `❯` and caret, blue text) with
  a `local mcp server` subtitle.
- Favicon: amber chevron on a black rounded square (not the stock Nix SVG).
- Motion: blinking caret in the wordmark + a subtle vertical scan pulse across the
  flake glyphs (~6s period).

## Changes

### 1. Palette tokens (`app/globals.css`)

Add `--amber: #f2b25c`. Amber is applied to exactly four surfaces: the prompt
`❯`, the blinking caret, the copied `✓`, and focus indicators (copy button, icon
links, and the field's focus border). Everything else stays blue.

### 2. Wordmark (`app/page.tsx`, `app/globals.css`)

Replace the single uppercase eyebrow with a two-line terminal header:

```
❯ nix-agent ▊        amber ❯ + caret, blue "nix-agent", lowercase mono
local mcp server     dim blue, uppercase, letter-spaced (old eyebrow style)
```

`❯` and the caret are `aria-hidden`; the accessible name remains
"nix-agent, local MCP server". The caret is a CSS block element that blinks via
`@keyframes`, solid (no blink) under `prefers-reduced-motion`.

### 3. Favicon (`public/nix-agent-mark.svg`, `app/layout.tsx`)

New SVG: a bold amber chevron drawn as a stroked path (not a font glyph, for
crisp 16px) on a black rounded square. Point `layout.tsx` `icons.icon` at it.
`public/nix-snowflake.svg` stays; it is still the WebGL point-mask.

### 4. Flake scan pulse (`lib/shaders.ts`, `__tests__/shaders.test.ts`)

Vertex shader derives `scanCoord` from the existing `baseNdc.y` (no
geometry-extent guessing), computes a wrap-safe gaussian band around a
time-driven position, gates it by the existing `motionEnabled` (off under reduced
motion), and passes a `vScan` varying to the fragment shader to lift brightness by
up to ~45% at the band peak. No new uniforms. Amplitude/width/speed are single
constants. A shader test asserts the `vScan`/scan path exists.

### 5. Agent face in the flake (`lib/snowflakeGeometry.ts`, `lib/shaders.ts`)

The snowflake becomes a face: two amber eyes and a faint amber mouth at the flake
center, so it reads as "the agent at the heart of Nix". Because the Nix flake has
a hollow center, the face is built from **dedicated added points**, not re-tinted
flake points.

- `buildAgentFacePoints(seed)` emits two eye discs + a shallow smile arc as glyph
  points in flake-local space, each carrying an `agent` flag (eye `1.0`, mouth
  `0.5`). Positions/radii are tunable constants.
- `concatGlyphPointData(flake, face)` appends the face after the flake and adds an
  `agent` buffer attribute (0 for flake points).
- Shaders: fragment tints `agent > 0` amber (eyes bright, mouth dim). Vertex makes
  eyes blink (~every 5s, quick) and gaze-shift toward `uPointer` (bounded; no
  effect off-screen), rendered slightly larger. All gated by `motionEnabled`, so
  reduced motion = steady forward-looking eyes.

Nudged the desktop flake right (`snowflakeHorizontalOffset` 0.52 -> 0.72) so it
stops clipping into the copy column.

## Verification

typecheck, lint, all tests (including the new shader assertion), production build.
Visual check on the running dev server (`:3000`); no browser extension available
for automated screenshots.
