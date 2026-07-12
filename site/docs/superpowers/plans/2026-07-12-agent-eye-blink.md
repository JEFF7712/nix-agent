# Agent Eye Blink (Lid Curtain) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the agent-face brightness-dip blink with an expressive descending lid curtain plus light Y-squash on sclera and pupil.

**Architecture:** Add an `eyeLocalY` per-point attribute from face geometry. The vertex shader drives an irregular blink envelope (long stares, fast close, brief shut, slower open, occasional double-blink), hides eye points above a descending lid line, and compresses eye Y near full close. Reduced motion keeps eyes open.

**Tech Stack:** TypeScript, Three.js `BufferGeometry` attributes, GLSL shaders, Vitest.

**Spec:** `site/docs/superpowers/specs/2026-07-12-agent-eye-blink-design.md`

---

## File map

| File | Responsibility |
| --- | --- |
| `site/lib/snowflakeGeometry.ts` | Emit `eyeLocalY` for eye points; zero for mouth; concat zeros for flake |
| `site/components/GlyphSnowflake.tsx` | Bind `eyeLocalY` buffer attribute |
| `site/lib/shaders.ts` | Expressive blink envelope, lid curtain, squash; remove brightness-only blink |
| `site/__tests__/snowflakeGeometry.test.ts` | Geometry attribute coverage |
| `site/__tests__/shaders.test.ts` | Shader path assertions |

---

### Task 1: `eyeLocalY` geometry attribute

**Files:**
- Modify: `site/lib/snowflakeGeometry.ts`
- Modify: `site/__tests__/snowflakeGeometry.test.ts`

- [ ] **Step 1: Write the failing tests**

Add to `buildAgentFacePoints` describe:

```ts
it("records eye-local Y for eyes and zeroes it for the mouth", () => {
  const face = buildAgentFacePoints(0x4e4958);
  expect(face.eyeLocalY).toHaveLength(face.count);

  for (let i = 0; i < face.count; i += 1) {
    if (face.agent[i] === AGENT_MOUTH) {
      expect(face.eyeLocalY[i]).toBe(0);
    } else if (face.agent[i] === AGENT_EYE || face.agent[i] === AGENT_PUPIL) {
      expect(Math.abs(face.eyeLocalY[i])).toBeGreaterThan(0);
      expect(Math.abs(face.eyeLocalY[i])).toBeLessThanOrEqual(0.05 + 1e-6);
    }
  }
});
```

Note: disc centers include the exact center sample where local Y is 0 — allow `>= 0` magnitude check via: eye points as a set must include both positive and negative `eyeLocalY`, and every mouth is 0. Prefer:

```ts
it("records eye-local Y for eyes and zeroes it for the mouth", () => {
  const face = buildAgentFacePoints(0x4e4958);
  expect(face.eyeLocalY).toHaveLength(face.count);

  const eyeLocals = Array.from({ length: face.count }, (_, i) => i)
    .filter((i) => face.agent[i] === AGENT_EYE || face.agent[i] === AGENT_PUPIL)
    .map((i) => face.eyeLocalY[i]);
  const mouthLocals = Array.from({ length: face.count }, (_, i) => i)
    .filter((i) => face.agent[i] === AGENT_MOUTH)
    .map((i) => face.eyeLocalY[i]);

  expect(mouthLocals.every((y) => y === 0)).toBe(true);
  expect(eyeLocals.some((y) => y < 0)).toBe(true);
  expect(eyeLocals.some((y) => y > 0)).toBe(true);
  expect(Math.max(...eyeLocals.map(Math.abs))).toBeLessThanOrEqual(0.05 + 1e-6);
});
```

Add to `concatGlyphPointData` test expectations:

```ts
expect(Array.from(merged.eyeLocalY.subarray(0, flake.count)).every((v) => v === 0)).toBe(true);
expect(merged.eyeLocalY.subarray(flake.count)).toEqual(face.eyeLocalY);
```

Import `AGENT_PUPIL` if not already imported.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm exec vitest run __tests__/snowflakeGeometry.test.ts`
Expected: FAIL — `eyeLocalY` missing on face data

- [ ] **Step 3: Implement `eyeLocalY`**

In `snowflakeGeometry.ts`:

1. Extend `AgentFaceData` with `readonly eyeLocalY: Float32Array`.
2. Change `pushDisc` to also append local `gy` into a `localYs: number[]` parameter.
3. In `buildAgentFacePoints`, push `0` into `localYs` for mouth samples; fill `eyeLocalY` Float32Array from `localYs`.
4. In `concatGlyphPointData`, allocate `eyeLocalY`, leave flake region zero, copy `face.eyeLocalY` after the flake.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm exec vitest run __tests__/snowflakeGeometry.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add site/lib/snowflakeGeometry.ts site/__tests__/snowflakeGeometry.test.ts
git commit -m "feat(site): add eyeLocalY for agent blink lid curtain"
```

---

### Task 2: Wire attribute on the snowflake mesh

**Files:**
- Modify: `site/components/GlyphSnowflake.tsx`

- [ ] **Step 1: Bind `eyeLocalY`**

In `replaceGeometryAttributes`, after the `agent` attribute:

```ts
geometry.setAttribute("eyeLocalY", new THREE.BufferAttribute(points.eyeLocalY, 1));
```

- [ ] **Step 2: Typecheck the component path**

Run: `pnpm exec tsc --noEmit -p tsconfig.json` from `site/`
Expected: PASS (or no errors related to `eyeLocalY`)

- [ ] **Step 3: Commit**

```bash
git add site/components/GlyphSnowflake.tsx
git commit -m "feat(site): bind eyeLocalY attribute on glyph snowflake"
```

---

### Task 3: Lid-curtain blink shader

**Files:**
- Modify: `site/lib/shaders.ts`
- Modify: `site/__tests__/shaders.test.ts`

- [ ] **Step 1: Write the failing shader tests**

Replace/extend the agent blink test:

```ts
it("closes agent eyes with a lid curtain, squash, and expressive timing", () => {
  expect(vertexShader).toContain("attribute float eyeLocalY");
  expect(vertexShader).toMatch(/lidY|lidThreshold|lid/);
  expect(vertexShader).toMatch(/eyeLocalY/);
  expect(vertexShader).toMatch(/squash/);
  expect(vertexShader).toMatch(/blinkAmt|blinkProgress|blink/);
  expect(vertexShader).toMatch(/motionEnabled/);
  expect(vertexShader).toMatch(/gaze[\s\S]*uPointer/);
  expect(vertexShader).not.toMatch(/blinkDip/);
  expect(vertexShader).not.toMatch(/vAgentBright\s*=\s*\([\s\S]*\)\s*\*\s*blink/);
  expect(fragmentShader).toMatch(/lit\s*=\s*mix\(vBrightness \* depthLight,\s*vAgentBright,\s*isAgent\)/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run __tests__/shaders.test.ts`
Expected: FAIL on missing `eyeLocalY` / lid path

- [ ] **Step 3: Implement shader blink**

In `vertexShader`:

1. Add `attribute float eyeLocalY;`.
2. Remove the old `blinkCycle` / `blinkDip` / brightness `* blink` path.
3. After computing `isEye` / `isPupil` / `isSclera`, compute expressive `blinkAmt` in `0..1`:
   - Long open fraction of a cycle (~2–6s feel via ~0.18–0.22 Hz base + hash variation)
   - Fast close (~0.28 of blink window), brief shut, slower open (~0.5+ of window)
   - Occasional double-blink via a second earlier pulse when `hash(epoch) > 0.7`
   - Multiply by `motionEnabled`
4. Apply **squash** on eye points before (or on) the position used for transform:

```glsl
float squash = mix(1.0, 0.18, blinkAmt * blinkAmt);
vec3 eyed = position;
eyed.y += eyeLocalY * (squash - 1.0) * isEye;
// use eyed instead of position for the rotation/breathing path for consistency,
// or apply the Y delta onto transformed after basePosition — prefer applying to
// pre-rotation position so lids track the face.
```

Practical integration: compute `blinkAmt` early; build `vec3 facePosition = position; facePosition.y += eyeLocalY * (squash - 1.0) * isEye;` then rotate `facePosition` instead of `position`.

5. **Lid curtain:** `lidY = mix(0.055, -0.05, blinkAmt);` then

```glsl
float lidVisible = 1.0 - isEye + isEye * smoothstep(lidY + 0.006, lidY - 0.004, eyeLocalY);
```

6. Multiply `gl_PointSize` by `lidVisible` for covered points; set

```glsl
vAgentBright = (isPupil * 1.25 + isSclera * 0.4) * mix(1.0, 0.9, blinkAmt) * lidVisible + isMouth * 0.42;
```

Keep mouth and gaze behavior otherwise unchanged. Do not change repel / scan / pointer paths.

- [ ] **Step 4: Run shader tests**

Run: `pnpm exec vitest run __tests__/shaders.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add site/lib/shaders.ts site/__tests__/shaders.test.ts
git commit -m "feat(site): expressive lid-curtain blink for agent eyes"
```

---

### Task 4: Full verification

- [ ] **Step 1: Run the site test suite**

Run: `pnpm exec vitest run` from `site/`
Expected: all tests PASS

- [ ] **Step 2: Visual checklist (manual)**

- Single blink reads as lid closing, not a brightness flicker
- Occasional double-blink appears
- Eyes stay open with `prefers-reduced-motion: reduce`
- Gaze and pointer repel still work; mouth unchanged

---

## Spec coverage

| Spec item | Task |
| --- | --- |
| `eyeLocalY` attribute | Task 1 |
| Wire attribute on mesh | Task 2 |
| Expressive envelope | Task 3 |
| Lid curtain | Task 3 |
| Squash at close | Task 3 |
| Remove brightness-only blink | Task 3 |
| Reduced motion gate | Task 3 |
| Geometry/shader tests | Tasks 1 & 3 |
| Visual check | Task 4 |
