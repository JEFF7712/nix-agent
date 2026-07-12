import { act, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as THREE from "three";

import {
  GlyphSnowflake,
  createGlyphPoints,
  createStaticGlyphFallback,
  getAnimationActivity,
  shouldHandlePointerWave,
  shouldRebuildDensity,
} from "../components/GlyphSnowflake";
import { CANONICAL_GLYPH_FALLBACK } from "../lib/glyphFallback";
import { DENSITY_TIERS } from "../lib/snowflakeGeometry";

describe("GlyphSnowflake lifecycle helpers", () => {
  it("only animates while visible and the document is visible", () => {
    expect(getAnimationActivity(true, "visible")).toBe(true);
    expect(getAnimationActivity(false, "visible")).toBe(false);
    expect(getAnimationActivity(true, "hidden")).toBe(false);
  });

  it("rebuilds point data only when the selected tier changes", () => {
    expect(shouldRebuildDensity(DENSITY_TIERS.desktop, DENSITY_TIERS.desktop)).toBe(false);
    expect(shouldRebuildDensity(DENSITY_TIERS.desktop, DENSITY_TIERS.high)).toBe(true);
  });

  it("updates the local wave for mouse or pen pointers but never touch steering", () => {
    expect(shouldHandlePointerWave("mouse", false)).toBe(true);
    expect(shouldHandlePointerWave("pen", false)).toBe(true);
    expect(shouldHandlePointerWave("touch", false)).toBe(false);
    expect(shouldHandlePointerWave("mouse", true)).toBe(false);
  });

  it("creates a dense deterministic ASCII fallback from a canonical alpha mask", () => {
    const alpha = new Uint8Array([
      0, 255, 0,
      255, 255, 255,
      0, 255, 0,
    ]);
    const first = createStaticGlyphFallback(alpha, 3, 3, 7);
    const second = createStaticGlyphFallback(alpha, 3, 3, 7);

    expect(first).toBe(second);
    expect(first.split("\n")).toHaveLength(3);
    expect(first.replaceAll(/[\s\n]/g, "").length).toBe(5);
  });
});

describe("GlyphSnowflake", () => {
  it("renders the canonical fallback before WebGL initialization", () => {
    const { container } = render(<GlyphSnowflake />);

    expect(container.querySelector("[data-glyph-fallback]")?.textContent).toBe(
      CANONICAL_GLYPH_FALLBACK,
    );
    expect(container.querySelector("canvas")).not.toBeInTheDocument();
  });

  it("keeps the canonical fallback visible when SVG loading fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { container } = render(<GlyphSnowflake />);

    await waitFor(() => expect(warning).toHaveBeenCalledOnce());
    expect(container.querySelector("[data-glyph-fallback]")?.textContent).toBe(
      CANONICAL_GLYPH_FALLBACK,
    );
    expect(container.querySelector("canvas")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("does not create WebGL after unmounting while fonts initialize", async () => {
    let resolveReady!: () => void;
    let resolveLoad!: () => void;
    const ready = new Promise<void>((resolve) => { resolveReady = resolve; });
    let readyObserved = false;
    const load = vi.fn(() => new Promise<FontFace[]>((resolve) => {
      resolveLoad = () => resolve([]);
    }));
    Object.defineProperty(document, "fonts", {
      configurable: true,
      value: {
        get ready() {
          readyObserved = true;
          return ready;
        },
        load,
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(new Blob(["<svg />"], { type: "image/svg+xml" })),
    }));
    vi.stubGlobal("Image", class {
      decoding = "";
      src = "";
      decode = vi.fn().mockResolvedValue(undefined);
    });
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:test"),
      revokeObjectURL: vi.fn(),
    });
    const context2d = {
      clearRect: vi.fn(),
      drawImage: vi.fn(),
      getImageData: vi.fn(() => ({ data: new Uint8ClampedArray(768 * 768 * 4) })),
      fillText: vi.fn(),
      set fillStyle(_value: string) {},
      set font(_value: string) {},
      set textAlign(_value: CanvasTextAlign) {},
      set textBaseline(_value: CanvasTextBaseline) {},
    } as unknown as CanvasRenderingContext2D;
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockImplementation((contextId: string) => contextId === "2d"
        ? context2d
        : {} as WebGL2RenderingContext);

    const { container, unmount } = render(<GlyphSnowflake />);
    await waitFor(() => expect(readyObserved).toBe(true));
    unmount();

    await act(async () => { resolveReady(); });
    await waitFor(() => expect(load).toHaveBeenCalledOnce());
    await act(async () => { resolveLoad(); });

    expect(getContext.mock.calls.filter(([contextId]) => contextId === "webgl2")).toHaveLength(0);
    expect(container.querySelector("canvas")).not.toBeInTheDocument();
    expect(container.querySelector(".glyph-snowflake")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("creates exactly one Points draw object from one geometry and material", () => {
    const geometry = new THREE.BufferGeometry();
    const material = new THREE.PointsMaterial();
    const scene = new THREE.Scene();

    scene.add(createGlyphPoints(geometry, material));

    expect(scene.children).toHaveLength(1);
    expect(scene.children[0]).toBeInstanceOf(THREE.Points);
    expect((scene.children[0] as THREE.Points).geometry).toBe(geometry);
    expect((scene.children[0] as THREE.Points).material).toBe(material);
  });
});
