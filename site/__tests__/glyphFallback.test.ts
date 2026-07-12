import { describe, expect, it } from "vitest";

import { CANONICAL_GLYPH_FALLBACK } from "../lib/glyphFallback";

describe("canonical glyph fallback", () => {
  it("is a dense, source-generated, recognizable snowflake at first paint", () => {
    const lines = CANONICAL_GLYPH_FALLBACK.split("\n");
    const occupied = CANONICAL_GLYPH_FALLBACK.replaceAll(/\s/g, "").length;
    const wideRows = lines.filter((line) => line.trim().length >= 64);

    expect(lines.length).toBeGreaterThanOrEqual(64);
    expect(Math.max(...lines.map((line) => line.length))).toBeGreaterThanOrEqual(64);
    expect(occupied).toBeGreaterThan(1_500);
    expect(wideRows.length).toBeGreaterThanOrEqual(6);
    expect(new Set(CANONICAL_GLYPH_FALLBACK.match(/[+*#=:@%&]/g))).toHaveLength(8);
  });
});
