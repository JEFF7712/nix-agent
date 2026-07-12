import { describe, expect, it, vi } from "vitest";
import type { WebGLRenderer } from "three";

import { validateAndRevealGlyphRenderer } from "../lib/shaderValidation";

function rendererWithLinkStatus(linked: boolean) {
  const gl = {
    LINK_STATUS: 0x8b82,
    getProgramParameter: vi.fn(() => linked),
  } as unknown as WebGL2RenderingContext;
  const renderer = {
    debug: { onShaderError: null as ((...args: unknown[]) => void) | null },
    compileAsync: vi.fn(async () => {
      renderer.debug.onShaderError?.(gl, {}, {}, {});
    }),
    render: vi.fn(),
  };
  return renderer;
}

describe("validateAndRevealGlyphRenderer", () => {
  it("rejects a failed link diagnostic even when compileAsync resolves", async () => {
    const renderer = rendererWithLinkStatus(false);
    const ready = vi.fn();
    const dispose = vi.fn();

    await expect(validateAndRevealGlyphRenderer({
      renderer: renderer as unknown as WebGLRenderer,
      scene: {} as never, camera: {} as never, ready, dispose,
    })).rejects.toThrow("shader");

    expect(renderer.compileAsync).toHaveResolved();
    expect(renderer.render).not.toHaveBeenCalled();
    expect(ready).not.toHaveBeenCalled();
    expect(dispose).toHaveBeenCalledOnce();
    expect(renderer.debug.onShaderError).toBeNull();
  });

  it("performs a first render before revealing a successfully linked renderer", async () => {
    const renderer = rendererWithLinkStatus(true);
    const ready = vi.fn();
    const dispose = vi.fn();

    await validateAndRevealGlyphRenderer({
      renderer: renderer as unknown as WebGLRenderer,
      scene: {} as never,
      camera: {} as never,
      ready,
      dispose,
    });

    expect(renderer.render).toHaveBeenCalledOnce();
    expect(renderer.render.mock.invocationCallOrder[0]).toBeLessThan(ready.mock.invocationCallOrder[0]);
    expect(ready).toHaveBeenCalledOnce();
    expect(dispose).not.toHaveBeenCalled();
    expect(renderer.debug.onShaderError).toBeNull();
  });

  it("makes a late compile resolution inert after teardown cancellation", async () => {
    let resolveCompile = () => {};
    const compile = new Promise<void>((resolve) => { resolveCompile = resolve; });
    const renderer = rendererWithLinkStatus(true);
    renderer.compileAsync.mockImplementation(() => compile);
    const controller = new AbortController();
    const ready = vi.fn();
    const dispose = vi.fn();
    const validation = validateAndRevealGlyphRenderer({
      renderer: renderer as unknown as WebGLRenderer,
      scene: {} as never,
      camera: {} as never,
      signal: controller.signal,
      ready,
      dispose,
    });

    controller.abort();
    dispose();
    resolveCompile();
    await validation;

    expect(renderer.render).not.toHaveBeenCalled();
    expect(ready).not.toHaveBeenCalled();
    expect(dispose).toHaveBeenCalledOnce();
    expect(renderer.debug.onShaderError).toBeNull();
  });
});
