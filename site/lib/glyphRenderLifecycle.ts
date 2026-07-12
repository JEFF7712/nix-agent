export interface GlyphRendererBoundary {
  readonly domElement: HTMLCanvasElement;
  render(scene: unknown, camera: unknown): void;
  setAnimationLoop(callback: ((time: number) => void) | null): void;
}

export const GLYPH_VISIBILITY_THRESHOLD = 0.01;

export interface GlyphRenderLifecycleOptions {
  readonly host: HTMLElement;
  readonly renderer: GlyphRendererBoundary;
  readonly scene: unknown;
  readonly camera: unknown;
  readonly reducedMotion: boolean;
  readonly resize: () => void;
  readonly dispose: () => void;
  readonly animate?: (time: number) => void;
  readonly pointerMove?: (event: PointerEvent) => void;
  readonly pointerLeave?: () => void;
  readonly pointerTarget?: Pick<EventTarget, "addEventListener" | "removeEventListener">;
  readonly contextLost?: (event: Event) => void;
  readonly createResizeObserver?: (callback: () => void) => Pick<ResizeObserver, "observe" | "disconnect">;
  readonly createIntersectionObserver?: (
    callback: (
      entries: readonly Pick<
        IntersectionObserverEntry,
        "isIntersecting" | "intersectionRatio"
      >[],
    ) => void,
  ) => Pick<IntersectionObserver, "observe" | "disconnect">;
}

export function startGlyphRenderLifecycle(options: GlyphRenderLifecycleOptions) {
  const {
    host, renderer, scene, camera, reducedMotion, dispose,
    animate = () => {}, pointerMove = () => {}, pointerLeave = () => {},
    contextLost = () => {},
  } = options;
  const pointerTarget = options.pointerTarget ?? (typeof window === "undefined" ? host : window);
  let intersecting = true;
  let cleaned = false;
  const render = () => renderer.render(scene, camera);
  const resize = () => {
    if (cleaned) return;
    options.resize();
    if (reducedMotion) render();
  };
  const updateLoop = () => {
    if (cleaned) return;
    const active = !reducedMotion && intersecting && document.visibilityState === "visible";
    renderer.setAnimationLoop(active ? (time) => {
      if (cleaned) return;
      animate(time);
      render();
    } : null);
    if (!reducedMotion && !active) render();
  };
  const visibility = () => updateLoop();
  const lost = (event: Event) => {
    event.preventDefault();
    cleanup();
    contextLost(event);
  };
  const createIntersectionObserver = options.createIntersectionObserver ?? (
    typeof IntersectionObserver === "undefined"
      ? null
      : (callback) => new IntersectionObserver(callback, {
          threshold: GLYPH_VISIBILITY_THRESHOLD,
        })
  );
  const createResizeObserver = options.createResizeObserver ?? (
    typeof ResizeObserver === "undefined" ? null : (callback) => new ResizeObserver(callback)
  );
  const intersection = createIntersectionObserver?.(([entry]) => {
    intersecting = entry.isIntersecting &&
      entry.intersectionRatio >= GLYPH_VISIBILITY_THRESHOLD;
    updateLoop();
  }) ?? null;
  const resizeObserver = createResizeObserver?.(resize) ?? null;

  renderer.domElement.dataset.glyphCanvas = "";
  host.appendChild(renderer.domElement);
  pointerTarget.addEventListener("pointermove", pointerMove as EventListener, { passive: true });
  pointerTarget.addEventListener("pointerleave", pointerLeave as EventListener);
  renderer.domElement.addEventListener("webglcontextlost", lost);
  document.addEventListener("visibilitychange", visibility);
  resizeObserver?.observe(host);
  intersection?.observe(host);
  resize();
  updateLoop();

  function cleanup() {
    if (cleaned) return;
    cleaned = true;
    renderer.setAnimationLoop(null);
    resizeObserver?.disconnect();
    intersection?.disconnect();
    pointerTarget.removeEventListener("pointermove", pointerMove as EventListener);
    pointerTarget.removeEventListener("pointerleave", pointerLeave as EventListener);
    renderer.domElement.removeEventListener("webglcontextlost", lost);
    document.removeEventListener("visibilitychange", visibility);
    dispose();
    renderer.domElement.remove();
  }

  return {
    resize,
    cleanup,
  };
}
