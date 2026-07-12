import { describe, expect, it, vi } from "vitest";

import { GLYPH_CHARACTERS } from "../lib/glyphCharacters";
import { createGlyphAtlas, createReadyGlyphAtlas } from "../lib/glyphAtlas";

describe("createGlyphAtlas", () => {
  it("lays out the fixed glyph set in a deterministic canvas grid", () => {
    const fillText = vi.fn();
    let font = "";
    const context = {
      clearRect: vi.fn(),
      fillText,
      set fillStyle(_value: string) {},
      set font(value: string) { font = value; },
      set textAlign(_value: CanvasTextAlign) {},
      set textBaseline(_value: CanvasTextBaseline) {},
    } as unknown as CanvasRenderingContext2D;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);

    const atlas = createGlyphAtlas("'Loaded Mono', monospace", {
      cellWidth: 20,
      cellHeight: 24,
      columns: 4,
    });

    expect(GLYPH_CHARACTERS).toBe("+*#=:@%&");
    expect(atlas.columns).toBe(4);
    expect(atlas.rows).toBe(2);
    expect(atlas.cellWidth).toBe(20);
    expect(atlas.cellHeight).toBe(24);
    expect(atlas.canvas.width).toBe(80);
    expect(atlas.canvas.height).toBe(48);
    expect(font).toBe("500 17px 'Loaded Mono', monospace");
    expect(fillText).toHaveBeenCalledTimes(GLYPH_CHARACTERS.length);
    expect(fillText).toHaveBeenNthCalledWith(1, "+", 10, 12);
    expect(fillText).toHaveBeenNthCalledWith(5, ":", 10, 36);
  });

  it("rejects an empty computed font family", () => {
    expect(() => createGlyphAtlas("   ")).toThrowError(
      new TypeError("fontFamily must be a nonempty string"),
    );
  });

  it("waits for font readiness and loading before drawing", async () => {
    const events: string[] = [];
    const ready = Promise.resolve().then(() => { events.push("ready"); });
    const load = vi.fn(async (font: string) => {
      events.push(`load:${font}`);
      return [];
    });
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: { ready, load },
    });
    const context = {
      clearRect: vi.fn(),
      fillText: vi.fn(() => { events.push("draw"); }),
      set fillStyle(_value: string) {},
      set font(_value: string) {},
      set textAlign(_value: CanvasTextAlign) {},
      set textBaseline(_value: CanvasTextBaseline) {},
    } as unknown as CanvasRenderingContext2D;
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);

    await createReadyGlyphAtlas("Computed Font, monospace", { cellHeight: 50 });

    expect(load).toHaveBeenCalledWith("500 36px Computed Font");
    expect(events.slice(0, 2)).toEqual([
      "ready",
      "load:500 36px Computed Font",
    ]);
    expect(events[2]).toBe("draw");
  });
});
