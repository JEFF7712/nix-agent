import { describe, expect, it } from "vitest";

import {
  DENSITY_TIERS,
  buildGlyphPointData,
  seededNoise,
  selectDensityTier,
} from "../lib/snowflakeGeometry";
import { GLYPH_CHARACTERS } from "../lib/glyphCharacters";

const filledMask = (width: number, height: number) =>
  new Uint8Array(width * height).fill(255);

describe("snowflake density", () => {
  it("selects bounded tiers for representative mobile, desktop, and high-density widths", () => {
    expect(selectDensityTier(390)).toBe(DENSITY_TIERS.mobile);
    expect(selectDensityTier(1280)).toBe(DENSITY_TIERS.desktop);
    expect(selectDensityTier(2200)).toBe(DENSITY_TIERS.high);
    expect(selectDensityTier(2200, 2)).toBe(DENSITY_TIERS.mobile);
    expect(selectDensityTier(2200, 4)).toBe(DENSITY_TIERS.desktop);
  });
});

describe("seededNoise", () => {
  it("is deterministic and bounded", () => {
    expect(seededNoise(17, 29, 41)).toBe(seededNoise(17, 29, 41));
    expect(seededNoise(17, 29, 41)).toBeGreaterThanOrEqual(0);
    expect(seededNoise(17, 29, 41)).toBeLessThan(1);
    expect(seededNoise(17, 29, 41)).not.toBe(seededNoise(17, 29, 42));
  });

  it("stays bounded across a representative hash sweep", () => {
    for (let seed = 0; seed < 10_000; seed += 1) {
      expect(seededNoise(seed, seed * 31, seed * 101)).toBeGreaterThanOrEqual(0);
      expect(seededNoise(seed, seed * 31, seed * 101)).toBeLessThan(1);
    }
    expect(seededNoise(0xdcd1bff9, 0, 0)).toBeLessThan(1);
  });
});

describe("buildGlyphPointData", () => {
  it("maps mask samples into aspect-correct canonical coordinates", () => {
    const tier = { ...DENSITY_TIERS.desktop, pointCap: 20 };
    const data = buildGlyphPointData({
      alpha: new Uint8Array([255, 0, 0, 255]),
      width: 2,
      height: 2,
      tier,
      seed: 9,
    });

    expect(data.count).toBe(2);
    expect(Array.from(data.positions.filter((_, index) => index % 3 === 0))).toEqual([
      -0.5, 0.5,
    ]);
    expect(Array.from(data.positions.filter((_, index) => index % 3 === 1))).toEqual([
      0.5, -0.5,
    ]);
  });

  it("is byte-identical for the same input and preserves all samples below the cap", () => {
    const input = {
      alpha: new Uint8Array([255, 128, 0, 64, 255, 0]),
      width: 3,
      height: 2,
      tier: { ...DENSITY_TIERS.mobile, pointCap: 10 },
      seed: 123,
    };
    const first = buildGlyphPointData(input);
    const second = buildGlyphPointData(input);

    expect(first.count).toBe(4);
    expect(first.positions).toEqual(second.positions);
    expect(first.glyphIndices).toEqual(second.glyphIndices);
    expect(first.brightness).toEqual(second.brightness);
    expect(first.phase).toEqual(second.phase);
    expect(first.baseSize).toEqual(second.baseSize);
  });

  it("never exceeds the tier cap and keeps samples distributed across the mask", () => {
    const tier = { ...DENSITY_TIERS.mobile, pointCap: 12 };
    const data = buildGlyphPointData({
      alpha: filledMask(20, 10),
      width: 20,
      height: 10,
      tier,
      seed: 4,
    });
    const xs = Array.from(data.positions.filter((_, index) => index % 3 === 0));
    const ys = Array.from(data.positions.filter((_, index) => index % 3 === 1));

    expect(data.count).toBe(12);
    expect(Math.min(...xs)).toBeLessThan(-0.7);
    expect(Math.max(...xs)).toBeGreaterThan(0.7);
    expect(Math.min(...ys)).toBeLessThan(-0.35);
    expect(Math.max(...ys)).toBeGreaterThan(0.35);
  });

  it("uses valid glyphs and shallow, bounded, approximately symmetric extrusion", () => {
    const tier = { ...DENSITY_TIERS.high, pointCap: 100, zDepth: 0.08 };
    const data = buildGlyphPointData({
      alpha: filledMask(9, 9),
      width: 9,
      height: 9,
      tier,
      seed: 51,
    });
    const zs = Array.from(data.positions.filter((_, index) => index % 3 === 2));
    const mean = zs.reduce((sum, value) => sum + value, 0) / zs.length;

    expect(Math.max(...data.glyphIndices)).toBeLessThan(GLYPH_CHARACTERS.length);
    expect(Math.min(...data.glyphIndices)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...zs)).toBeLessThanOrEqual(tier.zDepth);
    expect(Math.min(...zs)).toBeGreaterThanOrEqual(-tier.zDepth);
    expect(Math.abs(mean)).toBeLessThan(0.015);
  });

  it.each([2.5, -1, Number.NaN, Number.POSITIVE_INFINITY])(
    "rejects invalid pointCap %s before allocating output",
    (pointCap) => {
      expect(() => buildGlyphPointData({
        alpha: filledMask(2, 2),
        width: 2,
        height: 2,
        tier: { ...DENSITY_TIERS.mobile, pointCap },
      })).toThrowError(RangeError);
    },
  );

  it.each([-1, Number.NaN, Number.POSITIVE_INFINITY])(
    "rejects invalid zDepth %s",
    (zDepth) => {
      expect(() => buildGlyphPointData({
        alpha: filledMask(2, 2),
        width: 2,
        height: 2,
        tier: { ...DENSITY_TIERS.mobile, zDepth },
      })).toThrowError(RangeError);
    },
  );

  it.each([-1, 256, Number.NaN, Number.POSITIVE_INFINITY])(
    "rejects invalid alphaThreshold %s",
    (alphaThreshold) => {
      expect(() => buildGlyphPointData({
        alpha: filledMask(2, 2),
        width: 2,
        height: 2,
        tier: DENSITY_TIERS.mobile,
        alphaThreshold,
      })).toThrowError(RangeError);
    },
  );

  it.each([2.5, Number.NaN, Number.POSITIVE_INFINITY])("rejects invalid seed %s", (seed) => {
    expect(() => buildGlyphPointData({
      alpha: filledMask(2, 2),
      width: 2,
      height: 2,
      tier: DENSITY_TIERS.mobile,
      seed,
    })).toThrowError(RangeError);
  });

  it("keeps every output typed array consistent with count", () => {
    const data = buildGlyphPointData({
      alpha: filledMask(3, 2),
      width: 3,
      height: 2,
      tier: { ...DENSITY_TIERS.mobile, pointCap: 3 },
    });

    expect(data.count).toBe(3);
    expect(data.positions).toHaveLength(data.count * 3);
    expect(data.glyphIndices).toHaveLength(data.count);
    expect(data.brightness).toHaveLength(data.count);
    expect(data.phase).toHaveLength(data.count);
    expect(data.baseSize).toHaveLength(data.count);
  });
});
