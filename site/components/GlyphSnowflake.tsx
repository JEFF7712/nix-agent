"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import { createReadyGlyphAtlas } from "../lib/glyphAtlas";
import { GLYPH_CHARACTERS } from "../lib/glyphCharacters";
import { CANONICAL_GLYPH_FALLBACK } from "../lib/glyphFallback";
import { startGlyphRenderLifecycle } from "../lib/glyphRenderLifecycle";
import { validateAndRevealGlyphRenderer } from "../lib/shaderValidation";
import {
  type DensityTier,
  buildGlyphPointData,
  seededNoise,
  selectDensityTier,
} from "../lib/snowflakeGeometry";
import { fragmentShader, vertexShader } from "../lib/shaders";

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

export function shouldHandlePointerWave(pointerType: string, reducedMotion: boolean) {
  return !reducedMotion && pointerType !== "touch";
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
  const points = buildGlyphPointData({ ...mask, tier, seed: 0x4e4958, alphaThreshold: 18 });
  geometry.setAttribute("position", new THREE.BufferAttribute(points.positions, 3));
  geometry.setAttribute("glyph", new THREE.BufferAttribute(points.glyphIndices, 1, false));
  geometry.setAttribute("brightness", new THREE.BufferAttribute(points.brightness, 1));
  geometry.setAttribute("phase", new THREE.BufferAttribute(points.phase, 1));
  geometry.setAttribute("baseSize", new THREE.BufferAttribute(points.baseSize, 1));
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
        renderer.setClearColor(0x080808, 1);
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
        };
        const material = new THREE.ShaderMaterial({
          uniforms,
          vertexShader,
          fragmentShader,
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        });
        scene.add(createGlyphPoints(geometry, material));
        let resourcesDisposed = false;
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
          uniforms.uPointScale.value = Math.min(width, height) * 0.038;
          uniforms.uResolution.value.set(width, height);
          const nextTier = selectDensityTier(width, deviceMemory());
          if (shouldRebuildDensity(tier, nextTier)) {
            tier = nextTier;
            replaceGeometryAttributes(geometry, mask, tier);
          }
        };
        const pointerMove = (event: PointerEvent) => {
          if (!shouldHandlePointerWave(event.pointerType, reducedMotion)) return;
          const bounds = host.getBoundingClientRect();
          uniforms.uPointer.value.set(
            ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
            -(((event.clientY - bounds.top) / bounds.height) * 2 - 1),
          );
        };
        const pointerLeave = () => uniforms.uPointer.value.set(20, 20);
        await validateAndRevealGlyphRenderer({
          renderer,
          scene,
          camera,
          signal: abort.signal,
          dispose: cleanup,
          ready: () => {
            if (disposed) return;
            cleanup = startGlyphRenderLifecycle({
              host,
              renderer,
              scene,
              camera,
              reducedMotion,
              resize,
              animate: (time) => { uniforms.uTime.value = time / 1000; },
              pointerMove,
              pointerLeave,
              contextLost: () => setReady(false),
              dispose: () => {
                if (resourcesDisposed) return;
                resourcesDisposed = true;
                geometry.dispose();
                material.dispose();
                texture.dispose();
                renderer.dispose();
              },
            }).cleanup;
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
