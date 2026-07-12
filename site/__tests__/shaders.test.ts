import { describe, expect, it } from "vitest";

import { fragmentShader, vertexShader } from "../lib/shaders";

describe("glyph shaders", () => {
  it("implements autonomous rotation, breathing, pointer mutation, and point sizing", () => {
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
    const distance = vertexShader.indexOf("distance(");

    expect(vertexShader).toContain("uniform vec2 uResolution");
    expect(vertexShader).toMatch(/baseNdc[\s\S]*baseClipPosition\.xy\s*\/\s*baseClipPosition\.w/);
    expect(vertexShader).toMatch(/uResolution\.x\s*\/\s*uResolution\.y/);
    expect(projection).toBeGreaterThan(0);
    expect(distance).toBeGreaterThan(projection);
  });

  it("addresses the glyph atlas and discards transparent fragments", () => {
    expect(fragmentShader).toContain("gl_PointCoord");
    expect(fragmentShader).toContain("uAtlas");
    expect(fragmentShader).toContain("discard");
    expect(fragmentShader).toContain("vBrightness");
    expect(fragmentShader).toContain("vMutation");
  });

  it("selects a time-varying pointer mutation from the wrapped atlas", () => {
    expect(fragmentShader).toMatch(/uniform\s+float\s+uTime/);
    expect(fragmentShader).toMatch(/float\s+atlasSize\s*=\s*uAtlasGrid\.x\s*\*\s*uAtlasGrid\.y/);
    expect(fragmentShader).toMatch(/mutationOffset[\s\S]*uTime/);
    expect(fragmentShader).toMatch(/mutationGlyph\s*=\s*mod\([\s\S]*atlasSize/);
    expect(fragmentShader).toMatch(/mix\(vGlyph,\s*mutationGlyph,\s*mutationAmount\)/);
    expect(fragmentShader).toMatch(/mutationAmount[\s\S]*vMutation/);
  });

  it("localizes bounded position noise to the pointer mutation", () => {
    expect(vertexShader).toMatch(
      /float\s+noise\s*=\s*boundedNoise\([\s\S]*?\)\s*\*\s*0\.008\s*\*\s*mutation/,
    );
  });
});
