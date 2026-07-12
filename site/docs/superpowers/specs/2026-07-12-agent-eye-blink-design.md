# Agent eye blink (lid curtain)

Replace the snowflake agent-face brightness dip with an expressive eyelid
close that reads as a real blink on glyph-disc eyes.

## Decisions

- Approach: descending **lid curtain** plus a slight vertical **squash** at
  full close (not pure brightness fade, not dedicated lid geometry).
- Personality: **expressive** — long irregular stares, fast close, brief shut,
  slightly slower open; mostly singles with occasional double-blinks.
- Scope: agent sclera + pupil only. Mouth, flake glyphs, caret blink, and
  pointer/glitch behavior are unchanged.
- Reduced motion: eyes stay open; no lid animation (`motionEnabled` gate).

## Motion envelope

| Phase | Feel | Target timing |
| --- | --- | --- |
| Open stare | Irregular waits | Often ~2–6s, sometimes longer |
| Close | Fast lid sweep down | ~80–120ms |
| Shut | Thin slit hold | ~40–80ms |
| Open | Slightly slower than close | ~120–180ms |
| Double-blink | Two closes close together | Occasional, not every cycle |

Both eyes share one blink progress so they stay in sync. Gaze tracking toward
`uPointer` remains as today.

## Technical approach

### Geometry (`lib/snowflakeGeometry.ts`)

When building agent eye points, record each point’s **local Y** relative to
its eye center (new buffer attribute, e.g. `eyeLocalY`). Pupils and sclera
for the same eye use that eye’s center. Mouth and flake points get `0`.

`GlyphSnowflake` wires the attribute onto the `BufferGeometry` like the
existing `agent` attribute.

### Shaders (`lib/shaders.ts`)

1. Build an expressive blink progress `0 → 1 → 0` from `uTime` (irregular
   waits + rare double-blink), multiplied by `motionEnabled`.
2. **Lid curtain:** as progress rises, hide/dim eye points whose
   `eyeLocalY` is above a descending threshold (lid coming down over the
   disc). Apply to both sclera and pupil.
3. **Squash:** near full close, compress eye points slightly toward the eye
   midline in Y so the shut state softens into a slit instead of a hard clip.
4. Remove the current brightness-only blink (`vAgentBright *= blink` style
   dip) as the primary close cue. A tiny brightness soften at full shut is
   optional if it helps the slit read.

Mouth shading and flake lighting stay untouched. No amber / pointer-glitch
changes in this pass.

## Out of scope

- Dedicated eyelid point arcs or new lid meshes
- Mouth animation
- Wordmark caret blink
- Pointer mutation / glitch radius / brightening

## Verification

- Geometry tests: eye points expose local Y; mouth/flake stay `0`; both eyes
  centered correctly.
- Shader tests: lid-curtain + squash + expressive envelope path exist;
  brightness-only blink is gone; reduced-motion gate remains.
- Visual check: single blink, double-blink, and `prefers-reduced-motion:
  reduce` (eyes stay open).
