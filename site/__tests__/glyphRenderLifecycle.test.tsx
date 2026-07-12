import { StrictMode, useEffect, useRef } from "react";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  GLYPH_VISIBILITY_THRESHOLD,
  startGlyphRenderLifecycle,
} from "../lib/glyphRenderLifecycle";

function mocks(reducedMotion = true) {
  const canvas = document.createElement("canvas");
  const renderer = {
    domElement: canvas,
    render: vi.fn(),
    setAnimationLoop: vi.fn(),
  };
  const resize = vi.fn();
  const dispose = vi.fn();
  const resizeObserver = { observe: vi.fn(), disconnect: vi.fn() };
  const intersectionObserver = { observe: vi.fn(), disconnect: vi.fn() };
  let queuedResize = () => {};
  let queuedIntersection = (
    entries: readonly { isIntersecting: boolean; intersectionRatio: number }[],
  ) => { void entries; };
  const createResizeObserver = vi.fn((callback: () => void) => {
    queuedResize = callback;
    return resizeObserver;
  });
  const createIntersectionObserver = vi.fn((callback: typeof queuedIntersection) => {
    queuedIntersection = callback;
    return intersectionObserver;
  });
  return {
    canvas, renderer, resize, dispose, reducedMotion,
    resizeObserver, intersectionObserver, createResizeObserver, createIntersectionObserver,
    queuedResize: () => queuedResize(),
    queuedIntersection: (isIntersecting: boolean, intersectionRatio = isIntersecting ? 1 : 0) =>
      queuedIntersection([{ isIntersecting, intersectionRatio }]),
  };
}

describe("startGlyphRenderLifecycle", () => {
  it("requires visible area before starting the animation loop", () => {
    expect(GLYPH_VISIBILITY_THRESHOLD).toBeGreaterThan(0);

    const host = document.createElement("div");
    const state = mocks(false);
    const lifecycle = startGlyphRenderLifecycle({ host, ...state, scene: {}, camera: {} });
    state.queuedIntersection(true, 0);
    expect(state.renderer.setAnimationLoop).toHaveBeenLastCalledWith(null);
    state.queuedIntersection(true, GLYPH_VISIBILITY_THRESHOLD);
    expect(state.renderer.setAnimationLoop).toHaveBeenLastCalledWith(expect.any(Function));
    lifecycle.cleanup();
  });

  it("renders one fixed reduced-motion frame, keeps the loop stopped, and renders resizes", () => {
    const host = document.createElement("div");
    const state = mocks();
    const lifecycle = startGlyphRenderLifecycle({ host, ...state, scene: {}, camera: {} });

    expect(state.renderer.setAnimationLoop).toHaveBeenLastCalledWith(null);
    expect(state.renderer.render).toHaveBeenCalledTimes(1);
    expect(state.resize).toHaveBeenCalledTimes(1);

    lifecycle.resize();
    expect(state.renderer.render).toHaveBeenCalledTimes(2);
    lifecycle.cleanup();
  });

  it("owns one canvas and releases the loop, observers, listeners, and GPU disposables", () => {
    const host = document.createElement("div");
    const add = vi.spyOn(host, "addEventListener");
    const remove = vi.spyOn(host, "removeEventListener");
    const state = mocks(false);
    const lifecycle = startGlyphRenderLifecycle({ host, ...state, scene: {}, camera: {} });

    expect(host.querySelectorAll("canvas")).toHaveLength(1);
    expect(add).toHaveBeenCalledWith("pointermove", expect.any(Function), { passive: true });
    lifecycle.cleanup();
    expect(state.renderer.setAnimationLoop).toHaveBeenLastCalledWith(null);
    expect(state.dispose).toHaveBeenCalledTimes(1);
    expect(state.resizeObserver.disconnect).toHaveBeenCalledOnce();
    expect(state.intersectionObserver.disconnect).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledWith("pointermove", expect.any(Function));
    expect(host.querySelectorAll("canvas")).toHaveLength(0);
  });

  it("is StrictMode-remount safe without duplicate canvases or leaked ownership", () => {
    const states: ReturnType<typeof mocks>[] = [];
    function Harness() {
      const ref = useRef<HTMLDivElement>(null);
      useEffect(() => {
        const state = mocks();
        states.push(state);
        return startGlyphRenderLifecycle({
          host: ref.current!, ...state, scene: {}, camera: {},
        }).cleanup;
      }, []);
      return <div data-testid="host" ref={ref} />;
    }

    const result = render(<StrictMode><Harness /></StrictMode>);
    expect(result.getByTestId("host").querySelectorAll("canvas")).toHaveLength(1);
    expect(states).toHaveLength(2);
    expect(states[0].dispose).toHaveBeenCalledTimes(1);
    result.unmount();
    expect(states[1].dispose).toHaveBeenCalledTimes(1);
  });

  it("treats context loss as terminal and makes every queued callback inert", () => {
    const host = document.createElement("div");
    const state = mocks(false);
    const fallback = vi.fn();
    const lifecycle = startGlyphRenderLifecycle({
      host, ...state, scene: {}, camera: {}, contextLost: fallback,
    });
    expect(state.renderer.setAnimationLoop).toHaveBeenLastCalledWith(expect.any(Function));

    const lost = new Event("webglcontextlost", { cancelable: true });
    state.canvas.dispatchEvent(lost);

    expect(lost.defaultPrevented).toBe(true);
    expect(state.renderer.setAnimationLoop).toHaveBeenLastCalledWith(null);
    expect(state.dispose).toHaveBeenCalledOnce();
    expect(state.resizeObserver.disconnect).toHaveBeenCalledOnce();
    expect(state.intersectionObserver.disconnect).toHaveBeenCalledOnce();
    expect(fallback).toHaveBeenCalledOnce();
    expect(host.querySelector("canvas")).not.toBeInTheDocument();

    state.queuedResize();
    state.queuedIntersection(true);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(state.renderer.render).not.toHaveBeenCalled();
    expect(state.renderer.setAnimationLoop).toHaveBeenLastCalledWith(null);

    lifecycle.cleanup();
    expect(state.dispose).toHaveBeenCalledOnce();
  });
});
