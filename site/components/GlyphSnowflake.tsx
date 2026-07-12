"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import { createReadyGlyphAtlas } from "../lib/glyphAtlas";
import { GLYPH_CHARACTERS } from "../lib/glyphCharacters";
import { CANONICAL_GLYPH_FALLBACK } from "../lib/glyphFallback";
import {
  FACE_HAPPY_EVENT,
  PULSE_SLOT_COUNT,
  advanceWince,
  clickSpamAnger,
  combineFaceAnger,
  faceAngerFromPointer,
  faceCenterNdc,
  findFreePulseSlot,
  pulseFaceDistance,
  pulseLifeForScale,
  shouldTriggerWince,
  smoothEmotion,
} from "../lib/faceMood";
import { startGlyphRenderLifecycle } from "../lib/glyphRenderLifecycle";
import { validateAndRevealGlyphRenderer } from "../lib/shaderValidation";
import {
  type DensityTier,
  buildAgentFacePoints,
  buildGlyphPointData,
  concatGlyphPointData,
  seededNoise,
  selectDensityTier,
  snowflakeHorizontalOffset,
} from "../lib/snowflakeGeometry";
import { fragmentShader, vertexShader } from "../lib/shaders";

export const SNOWFLAKE_CLEAR_COLOR = 0x000000;

const MASK_SIZE = 768;
type Mask = { alpha: Uint8ClampedArray; width: number; height: number };
type NavigatorWithMemory = Navigator & { readonly deviceMemory?: number };

function deviceMemory() {
  return (navigator as NavigatorWithMemory).deviceMemory;
}

export function getAnimationActivity(isIntersecting: boolean, visibility: DocumentVisibilityState) {
  return isIntersecting && visibility === "visible";
}

export function shouldRebuildDensity(previous: DensityTier, next: DensityTier) {
  return previous.name !== next.name;
}

export function shouldHandlePointerReaction(pointerType: string, reducedMotion: boolean) {
  return !reducedMotion && pointerType === "mouse";
}

export function createStaticGlyphFallback(
  alpha: Uint8Array | Uint8ClampedArray,
  width: number,
  height: number,
  seed = 41,
) {
  const lines: string[] = [];
  for (let row = 0; row < height; row += 1) {
    let line = "";
    for (let column = 0; column < width; column += 1) {
      const index = row * width + column;
      line += alpha[index] > 20
        ? GLYPH_CHARACTERS[Math.floor(seededNoise(column, row, seed) * GLYPH_CHARACTERS.length)]
        : " ";
    }
    lines.push(line.trimEnd());
  }
  return lines.join("\n");
}

function createCanonicalFallback(mask: Mask) {
  const width = 96;
  const height = 96;
  const alpha = new Uint8ClampedArray(width * height);
  for (let row = 0; row < height; row += 1) {
    for (let column = 0; column < width; column += 1) {
      const sourceX = Math.floor(((column + 0.5) / width) * mask.width);
      const sourceY = Math.floor(((row + 0.5) / height) * mask.height);
      alpha[row * width + column] = mask.alpha[sourceY * mask.width + sourceX];
    }
  }
  return createStaticGlyphFallback(alpha, width, height);
}

async function loadCanonicalMask(signal: AbortSignal): Promise<Mask> {
  const response = await fetch("/nix-snowflake.svg", { signal });
  if (!response.ok) throw new Error(`Snowflake SVG request failed: ${response.status}`);
  const svg = await response.blob();
  const url = URL.createObjectURL(svg);
  try {
    const image = new Image();
    image.decoding = "async";
    image.src = url;
    await image.decode();
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    const canvas = document.createElement("canvas");
    canvas.width = MASK_SIZE;
    canvas.height = MASK_SIZE;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("Canvas 2D context is unavailable for SVG mask");
    context.clearRect(0, 0, MASK_SIZE, MASK_SIZE);
    context.drawImage(image, 0, 0, MASK_SIZE, MASK_SIZE);
    const rgba = context.getImageData(0, 0, MASK_SIZE, MASK_SIZE).data;
    const alpha = new Uint8ClampedArray(MASK_SIZE * MASK_SIZE);
    for (let index = 0; index < alpha.length; index += 1) alpha[index] = rgba[index * 4 + 3];
    return { alpha, width: MASK_SIZE, height: MASK_SIZE };
  } finally {
    URL.revokeObjectURL(url);
  }
}

function replaceGeometryAttributes(geometry: THREE.BufferGeometry, mask: Mask, tier: DensityTier) {
  const flake = buildGlyphPointData({ ...mask, tier, seed: 0x4e4958, alphaThreshold: 18 });
  const points = concatGlyphPointData(flake, buildAgentFacePoints(0x4e4958));
  geometry.setAttribute("position", new THREE.BufferAttribute(points.positions, 3));
  geometry.setAttribute("glyph", new THREE.BufferAttribute(points.glyphIndices, 1, false));
  geometry.setAttribute("brightness", new THREE.BufferAttribute(points.brightness, 1));
  geometry.setAttribute("phase", new THREE.BufferAttribute(points.phase, 1));
  geometry.setAttribute("baseSize", new THREE.BufferAttribute(points.baseSize, 1));
  geometry.setAttribute("agent", new THREE.BufferAttribute(points.agent, 1));
  geometry.setAttribute("eyeLocalX", new THREE.BufferAttribute(points.eyeLocalX, 1));
  geometry.setAttribute("eyeLocalY", new THREE.BufferAttribute(points.eyeLocalY, 1));
  geometry.setDrawRange(0, points.count);
  geometry.computeBoundingSphere();
}

export function createGlyphPoints(
  geometry: THREE.BufferGeometry,
  material: THREE.Material,
) {
  return new THREE.Points(geometry, material);
}

export function GlyphSnowflake() {
  const hostRef = useRef<HTMLDivElement>(null);
  const [fallback, setFallback] = useState(CANONICAL_GLYPH_FALLBACK);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const abort = new AbortController();
    let disposed = false;
    let cleanup = () => {};

    void (async () => {
      try {
        const mask = await loadCanonicalMask(abort.signal);
        if (disposed) return;
        setFallback(createCanonicalFallback(mask));

        const fontFamily = getComputedStyle(host).fontFamily;
        const atlas = await createReadyGlyphAtlas(fontFamily, { cellWidth: 96, cellHeight: 96 });
        if (disposed || abort.signal.aborted) return;

        const probe = document.createElement("canvas");
        const context = probe.getContext("webgl2", { alpha: true, antialias: true });
        if (!context) throw new Error("WebGL2 is unavailable");
        const texture = new THREE.CanvasTexture(atlas.canvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.needsUpdate = true;
        const renderer = new THREE.WebGLRenderer({ canvas: probe, context, alpha: true, antialias: true });
        renderer.setClearColor(SNOWFLAKE_CLEAR_COLOR, 1);
        renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 10);
        camera.position.z = 3.15;
        const geometry = new THREE.BufferGeometry();
        let tier = selectDensityTier(host.clientWidth, deviceMemory());
        replaceGeometryAttributes(geometry, mask, tier);
        const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
        const uniforms = {
          uTime: { value: 0 },
          uPointer: { value: new THREE.Vector2(20, 20) },
          uReducedMotion: { value: reducedMotion ? 1 : 0 },
          uPointScale: { value: 28 },
          uResolution: { value: new THREE.Vector2(1, 1) },
          uAtlas: { value: texture },
          uAtlasGrid: { value: new THREE.Vector2(atlas.columns, atlas.rows) },
          uAnger: { value: 0 },
          uHappy: { value: 0 },
          uHappyBlink: { value: -1 },
          uSleepy: { value: 0 },
          uWake: { value: 0 },
          uPointerBlend: { value: 0 },
          uWinceAge: { value: -1 },
          uPulseOrigins: {
            value: Array.from({ length: PULSE_SLOT_COUNT }, () => new THREE.Vector2()),
          },
          uPulseAges: { value: Array.from({ length: PULSE_SLOT_COUNT }, () => -1) },
          uPulseScales: { value: Array.from({ length: PULSE_SLOT_COUNT }, () => 1) },
        };
        const material = new THREE.ShaderMaterial({
          uniforms,
          vertexShader,
          fragmentShader,
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        });
        const points = createGlyphPoints(geometry, material);
        scene.add(points);
        let resourcesDisposed = false;
        let lastPointer = { x: 20, y: 20, time: performance.now() };
        let pointerSpeed = 0;
        let clickTimes: number[] = [];
        let pulseClickTimes: number[] = [];
        let spamAnger = 0;
        let angerTarget = 0;
        let happyTarget = 0;
        let happyHold = 0;
        let pointerBlendTarget = 0;
        let winceAge = -1;
        let winceCooldown = 0;
        let lastInteract = performance.now();
        let startedAt = 0;
        let animOriginMs: number | null = null;
        const noteInteract = () => {
          lastInteract = performance.now();
        };
        cleanup = () => {
          if (resourcesDisposed) return;
          resourcesDisposed = true;
          renderer.setAnimationLoop(null);
          geometry.dispose();
          material.dispose();
          texture.dispose();
          renderer.dispose();
          renderer.domElement.remove();
        };
        const resize = () => {
          const width = Math.max(host.clientWidth, 1);
          const height = Math.max(host.clientHeight, 1);
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
          points.position.x = snowflakeHorizontalOffset(width);
          uniforms.uPointScale.value = Math.min(width, height) * 0.038;
          uniforms.uResolution.value.set(width, height);
          const nextTier = selectDensityTier(width, deviceMemory());
          if (shouldRebuildDensity(tier, nextTier)) {
            tier = nextTier;
            replaceGeometryAttributes(geometry, mask, tier);
          }
        };
        const pointerNdc = (event: PointerEvent) => {
          const bounds = host.getBoundingClientRect();
          return {
            x: ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
            y: -(((event.clientY - bounds.top) / bounds.height) * 2 - 1),
          };
        };
        const updateAnger = (pointerX: number, pointerY: number) => {
          if (reducedMotion) {
            angerTarget = 0;
            uniforms.uAnger.value = 0;
            return;
          }
          const face = faceCenterNdc(host.clientWidth);
          const pointerAnger = faceAngerFromPointer({
            pointerX,
            pointerY,
            faceX: face.x,
            faceY: face.y,
            speedNdc: pointerSpeed,
          });
          angerTarget = combineFaceAnger(pointerAnger, spamAnger);
        };
        const pointerMove = (event: PointerEvent) => {
          if (!shouldHandlePointerReaction(event.pointerType, reducedMotion)) return;
          const { x: pointerX, y: pointerY } = pointerNdc(event);
          const now = performance.now();
          const dt = Math.max((now - lastPointer.time) / 1000, 1 / 120);
          const dx = pointerX - lastPointer.x;
          const dy = pointerY - lastPointer.y;
          pointerSpeed = Math.hypot(dx, dy) / dt;
          lastPointer = { x: pointerX, y: pointerY, time: now };
          uniforms.uPointer.value.set(pointerX, pointerY);
          pointerBlendTarget = 1;
          noteInteract();
          updateAnger(pointerX, pointerY);
        };
        const pointerLeave = () => {
          // Keep last pointer for a soft gaze crossfade; kill interactivity via blend.
          pointerSpeed = 0;
          pointerBlendTarget = 0;
          lastPointer = { ...lastPointer, time: performance.now() };
          angerTarget = 0;
          spamAnger = 0;
        };
        const documentPointerLeave = (event: PointerEvent) => {
          if (event.relatedTarget == null) pointerLeave();
        };
        const pointerDown = (event: PointerEvent) => {
          if (!shouldHandlePointerReaction(event.pointerType, reducedMotion)) return;
          if (event.button !== 0) return;
          const { x, y } = pointerNdc(event);
          const now = performance.now();
          uniforms.uPointer.value.set(x, y);
          noteInteract();
          clickTimes = [...clickTimes.filter((time) => now - time <= 1800), now];
          pulseClickTimes = [...pulseClickTimes.filter((time) => now - time <= 520), now];
          const streak = pulseClickTimes.length;
          const scale = Math.min(6, 1.28 ** (streak - 1));
          const slot = findFreePulseSlot(uniforms.uPulseAges.value);
          if (slot >= 0) {
            uniforms.uPulseOrigins.value[slot].set(x, y);
            uniforms.uPulseAges.value[slot] = 0;
            uniforms.uPulseScales.value[slot] = scale;
          }
          const face = faceCenterNdc(host.clientWidth);
          const aspect = Math.max(host.clientWidth, 1) / Math.max(host.clientHeight, 1);
          if (
            shouldTriggerWince({
              pulseScale: scale,
              distance: pulseFaceDistance(x, y, face.x, face.y, aspect),
              winceAge,
              winceCooldown,
            })
          ) {
            winceAge = 0;
            uniforms.uWinceAge.value = 0;
          }
          spamAnger = clickSpamAnger(clickTimes, now);
          lastPointer = { x, y, time: now };
          pointerBlendTarget = 1;
          updateAnger(x, y);
        };
        const onHappy = () => {
          if (reducedMotion) return;
          happyTarget = 1;
          uniforms.uHappyBlink.value = 0;
          happyHold = 0.75;
          noteInteract();
        };
        window.addEventListener(FACE_HAPPY_EVENT, onHappy);
        window.addEventListener("pointerdown", pointerDown);
        document.documentElement.addEventListener("pointerleave", documentPointerLeave);
        const previousCleanup = cleanup;
        cleanup = () => {
          window.removeEventListener(FACE_HAPPY_EVENT, onHappy);
          window.removeEventListener("pointerdown", pointerDown);
          document.documentElement.removeEventListener("pointerleave", documentPointerLeave);
          previousCleanup();
        };
        await validateAndRevealGlyphRenderer({
          renderer,
          scene,
          camera,
          signal: abort.signal,
          dispose: cleanup,
          ready: () => {
            if (disposed) return;
            startedAt = performance.now();
            animOriginMs = null;
            const lifecycleCleanup = startGlyphRenderLifecycle({
              host,
              renderer,
              scene,
              camera,
              reducedMotion,
              resize,
              pointerTarget: window,
              animate: (time) => {
                // Local clock from first frame — absolute rAF time jumps after async
                // load and made the flake snap through a fast rotation on reveal.
                if (animOriginMs == null) animOriginMs = time;
                const seconds = (time - animOriginMs) / 1000;
                const previous = uniforms.uTime.value;
                const dt = previous > 0 || seconds > 0 ? Math.min(Math.max(seconds - previous, 0), 0.05) : 0;
                uniforms.uTime.value = seconds;
                const wakeAge = (performance.now() - startedAt) / 1000;
                uniforms.uWake.value = reducedMotion
                  ? 1
                  : Math.min(1, Math.max(0, (wakeAge - 0.25) / 0.55));
                const idleSec = (performance.now() - lastInteract) / 1000;
                const sleepyTarget = reducedMotion
                  ? 0
                  : Math.min(1, Math.max(0, (idleSec - 14) / 8));
                uniforms.uSleepy.value = smoothEmotion(
                  uniforms.uSleepy.value,
                  sleepyTarget,
                  dt,
                  1.2,
                  3.5,
                );
                uniforms.uPointerBlend.value = smoothEmotion(
                  uniforms.uPointerBlend.value,
                  pointerBlendTarget,
                  dt,
                  9,
                  0.75,
                );
                if (happyHold > 0) {
                  happyHold = Math.max(0, happyHold - dt);
                  happyTarget = 1;
                } else if (happyTarget > 0) {
                  happyTarget = Math.max(0, happyTarget - dt * 0.28);
                }
                uniforms.uHappy.value = smoothEmotion(
                  uniforms.uHappy.value,
                  happyTarget,
                  dt,
                  2.4,
                  1.5,
                );
                if (uniforms.uHappyBlink.value >= 0) {
                  uniforms.uHappyBlink.value += dt;
                  if (uniforms.uHappyBlink.value > 0.45) uniforms.uHappyBlink.value = -1;
                }
                uniforms.uAnger.value = smoothEmotion(uniforms.uAnger.value, angerTarget, dt, 9, 1.8);
                ({ age: winceAge, cooldown: winceCooldown } = advanceWince(winceAge, winceCooldown, dt));
                uniforms.uWinceAge.value = winceAge;
                for (let i = 0; i < PULSE_SLOT_COUNT; i += 1) {
                  const age = uniforms.uPulseAges.value[i];
                  if (age < 0) continue;
                  const nextAge = age + dt;
                  if (nextAge > pulseLifeForScale(uniforms.uPulseScales.value[i])) {
                    uniforms.uPulseAges.value[i] = -1;
                  } else {
                    uniforms.uPulseAges.value[i] = nextAge;
                  }
                }
                pointerSpeed *= Math.exp(-dt * 4);
                const now = performance.now();
                clickTimes = clickTimes.filter((stamp) => now - stamp <= 1800);
                pulseClickTimes = pulseClickTimes.filter((stamp) => now - stamp <= 520);
                spamAnger = clickSpamAnger(clickTimes, now);
                if (lastPointer.x <= 2) {
                  updateAnger(lastPointer.x, lastPointer.y);
                }
              },
              pointerMove,
              pointerLeave,
              contextLost: () => setReady(false),
              dispose: () => {
                if (resourcesDisposed) return;
                resourcesDisposed = true;
                window.removeEventListener(FACE_HAPPY_EVENT, onHappy);
                window.removeEventListener("pointerdown", pointerDown);
                document.documentElement.removeEventListener("pointerleave", documentPointerLeave);
                geometry.dispose();
                material.dispose();
                texture.dispose();
                renderer.dispose();
              },
            }).cleanup;
            cleanup = () => {
              window.removeEventListener(FACE_HAPPY_EVENT, onHappy);
              window.removeEventListener("pointerdown", pointerDown);
              document.documentElement.removeEventListener("pointerleave", documentPointerLeave);
              lifecycleCleanup();
            };
            setReady(true);
          },
        });
      } catch (error) {
        cleanup();
        if (!abort.signal.aborted) {
          console.warn("Glyph snowflake renderer fell back to static ASCII", error);
          setReady(false);
        }
      }
    })();

    return () => {
      disposed = true;
      abort.abort();
      cleanup();
    };
  }, []);

  return (
    <div className="glyph-snowflake" ref={hostRef}>
      <pre aria-hidden="true" className="glyph-snowflake-fallback" data-glyph-fallback hidden={ready}>
        {fallback}
      </pre>
    </div>
  );
}
