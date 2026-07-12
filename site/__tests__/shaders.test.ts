import { describe, expect, it } from "vitest";

import { fragmentShader, vertexShader } from "../lib/shaders";

describe("glyph shaders", () => {
  it("implements autonomous rotation, breathing, and point sizing", () => {
    expect(vertexShader).toContain("uniform float uTime");
    expect(vertexShader).toContain("uniform vec2 uPointer");
    expect(vertexShader).toContain("attribute float glyph");
    expect(vertexShader).toContain("attribute float brightness");
    expect(vertexShader).toContain("attribute float phase");
    expect(vertexShader).toContain("attribute float baseSize");
    expect(vertexShader).toMatch(/rotationX|rotateX/);
    expect(vertexShader).toMatch(/rotationY|rotateY/);
    expect(vertexShader).toContain("uReducedMotion");
    expect(vertexShader).toContain("gl_PointSize");
    expect(vertexShader).not.toMatch(/\bfloat\s+active\b/);
    expect(vertexShader).toMatch(/float xAngle\s*=.*sin\(uTime/);
    expect(vertexShader).toMatch(/float yAngle\s*=.*sin\(uTime/);
  });

  it("projects the rotated base position before aspect-correct pointer influence", () => {
    const projection = vertexShader.indexOf("baseClipPosition");
    const distance = vertexShader.indexOf("pointerDistance");

    expect(vertexShader).toContain("uniform vec2 uResolution");
    expect(vertexShader).toMatch(/baseNdc[\s\S]*baseClipPosition\.xy\s*\/\s*baseClipPosition\.w/);
    expect(vertexShader).toMatch(/uResolution\.x\s*\/\s*(max\()?uResolution\.y/);
    expect(projection).toBeGreaterThan(0);
    expect(distance).toBeGreaterThan(projection);
  });

  it("addresses the glyph atlas and discards transparent fragments", () => {
    expect(fragmentShader).toContain("gl_PointCoord");
    expect(fragmentShader).toContain("uAtlas");
    expect(fragmentShader).toContain("discard");
    expect(fragmentShader).toContain("vBrightness");
    expect(fragmentShader).toContain("vRepel");
  });

  it("shoves flake glyphs away from the aspect-correct pointer position", () => {
    expect(vertexShader).toMatch(/pointerDelta\s*=\s*baseNdc\s*-\s*uPointer/);
    expect(vertexShader).toMatch(
      /pointerDistance\s*=\s*length\(pointerDelta\s*\*\s*vec2\(aspect,\s*1\.0\)\)/,
    );
    expect(vertexShader).toMatch(
      /repelField\s*=\s*exp\(-pointerDistance\s*\*\s*pointerDistance[\s\S]*motionEnabled/,
    );
    expect(vertexShader).toMatch(/repelDir\s*=\s*normalize\(pointerDelta/);
    expect(vertexShader).toMatch(/transformed\.xy\s*\+=\s*repelDir\s*\*\s*repel/);
  });

  it("exempts the agent face from the repulsion field", () => {
    expect(vertexShader).toMatch(/isFace\s*=\s*step\(0\.25,\s*agent\)/);
    expect(vertexShader).toMatch(/repel\s*=\s*repelField\s*\*\s*\(1\.0\s*-\s*isFace\)/);
  });

  it("brightens the pushed rim without recoloring it", () => {
    expect(vertexShader).toContain("varying float vRepel");
    expect(fragmentShader).toContain("varying float vRepel");
    expect(fragmentShader).toMatch(/energy\s*=\s*1\.0\s*\+\s*vScan\s*\+\s*vRepel/);
    expect(fragmentShader).toMatch(/nixBlue\s*\*\s*lit\s*\*\s*energy/);
  });

  it("sweeps a reduced-motion-gated scan pulse from screen-space rows into the fragment", () => {
    expect(vertexShader).toContain("varying float vScan");
    expect(fragmentShader).toContain("varying float vScan");
    expect(vertexShader).toMatch(/scanCoord\s*=[\s\S]*baseNdc\.y/);
    expect(vertexShader).toMatch(/float\s+scan\s*=[\s\S]*motionEnabled/);
    expect(vertexShader).toContain("vScan = scan");
    expect(fragmentShader).toMatch(/1\.0\s*\+\s*vScan/);
  });

  it("closes agent eyes with a lid curtain, squash, and expressive timing", () => {
    expect(vertexShader).toContain("attribute float agent");
    expect(vertexShader).toContain("attribute float eyeLocalY");
    expect(vertexShader).toMatch(/isEye\s*=\s*step\([\s\S]*agent/);
    expect(vertexShader).toMatch(/isPupil\s*=\s*step\([\s\S]*agent/);
    expect(vertexShader).toMatch(/gaze[\s\S]*uPointer/);
    expect(vertexShader).toMatch(/transformed\.xy\s*\+=\s*gaze[\s\S]*isPupil/);
    expect(vertexShader).toMatch(/blinkAmt|agentBlinkAmount/);
    expect(vertexShader).toMatch(/lidY/);
    expect(vertexShader).toMatch(/squash/);
    expect(vertexShader).toMatch(/eyeLocalY/);
    expect(vertexShader).toMatch(/motionEnabled/);
    expect(vertexShader).not.toMatch(/blinkDip/);
    expect(vertexShader).not.toMatch(/vAgentBright\s*=\s*\([\s\S]*\)\s*\*\s*blink\b/);
    expect(fragmentShader).toContain("varying float vAgent");
    expect(fragmentShader).toMatch(/lit\s*=\s*mix\(vBrightness \* depthLight,\s*vAgentBright,\s*isAgent\)/);
    expect(fragmentShader).not.toMatch(/amber/i);
  });

  it("squashes sclera toward gaze and shades brows separately from the mouth", () => {
    expect(vertexShader).toContain("attribute float eyeLocalX");
    expect(vertexShader).toMatch(/interestLocal[\s\S]*isSclera/);
    expect(vertexShader).toMatch(/isBrow/);
    expect(vertexShader).toMatch(/isBrow\s*\*\s*0\.72/);
    expect(vertexShader).toMatch(/isMouth\s*\*\s*0\.42/);
  });

  it("morphs brows and mouth from anger and happy uniforms", () => {
    expect(vertexShader).toContain("uniform float uAnger");
    expect(vertexShader).toContain("uniform float uHappy");
    expect(vertexShader).toMatch(/innerBrow[\s\S]*anger/);
    expect(vertexShader).toMatch(/isMouth[\s\S]*happy/);
    expect(vertexShader).toMatch(/anger\s*=\s*clamp\(uAnger[\s\S]*uHappy/);
  });

  it("expands overlapping click pulse rings through the snowflake glyphs", () => {
    expect(vertexShader).toContain("uniform vec2 uPulseOrigins[8]");
    expect(vertexShader).toContain("uniform float uPulseAges[8]");
    expect(vertexShader).toContain("uniform float uPulseScales[8]");
    expect(vertexShader).toMatch(/for\s*\(\s*int\s+i\s*=\s*0;\s*i\s*<\s*8;\s*i\+\+\)/);
    expect(vertexShader).toMatch(/radius\s*=\s*pulseAge\s*\*\s*0\.7\s*\*\s*pulseScale/);
    expect(vertexShader).toMatch(/pulsePush\s*\+=\s*pulseDir/);
    expect(vertexShader).toMatch(/transformed\.xy\s*\+=\s*pulsePush/);
    expect(fragmentShader).toContain("varying float vPulse");
    expect(fragmentShader).toMatch(/vPulse/);
  });

  it("adds copy-happy sparkle and double-blink", () => {
    expect(vertexShader).toContain("uniform float uHappyBlink");
    expect(vertexShader).toMatch(/happyDoubleBlink/);
    expect(vertexShader).toMatch(/sparkle/);
    expect(vertexShader).toMatch(/glint/);
    expect(vertexShader).not.toMatch(/happyShimmer/);
    expect(fragmentShader).not.toMatch(/vHappyShimmer/);
  });

  it("supports idle gaze, curious tilt, sleepy lids, pulse wince, and wake-in", () => {
    expect(vertexShader).toContain("uniform float uSleepy");
    expect(vertexShader).toContain("uniform float uWake");
    expect(vertexShader).toContain("uniform float uPointerBlend");
    expect(vertexShader).toMatch(/idleGaze/);
    expect(vertexShader).toMatch(/tilt/);
    expect(vertexShader).toMatch(/wince/);
    expect(vertexShader).toContain("uniform float uWinceAge");
    expect(vertexShader).toMatch(/One-shot flinch|uWinceAge/);
    expect(vertexShader).toMatch(/settle/);
    expect(vertexShader).toMatch(/agentBlinkAmount\([\s\S]*sleepy/);
  });
});
