import type { Camera, Object3D, WebGLRenderer } from "three";

type ShaderValidationRenderer = Pick<WebGLRenderer, "debug" | "compileAsync" | "render">;

interface ShaderValidationOptions {
  readonly renderer: ShaderValidationRenderer;
  readonly scene: Object3D;
  readonly camera: Camera;
  readonly ready: () => void;
  readonly dispose: () => void;
  readonly signal?: AbortSignal;
}

export async function validateAndRevealGlyphRenderer({
  renderer, scene, camera, ready, dispose, signal,
}: ShaderValidationOptions) {
  if (signal?.aborted) return;
  const previous = renderer.debug.onShaderError;
  let shaderFailed = false;
  renderer.debug.onShaderError = (gl, program, vertex, fragment) => {
    if (!gl.getProgramParameter(program as unknown as globalThis.WebGLProgram, gl.LINK_STATUS)) {
      shaderFailed = true;
    }
    previous?.(gl, program, vertex, fragment);
  };
  try {
    await renderer.compileAsync(scene, camera);
    if (signal?.aborted) return;
    if (shaderFailed) throw new Error("Glyph shader compilation or link validation failed");
    if (signal?.aborted) return;
    renderer.render(scene, camera);
    if (signal?.aborted) return;
    if (shaderFailed) throw new Error("Glyph shader failed during first render validation");
    if (signal?.aborted) return;
    ready();
  } catch (error) {
    if (signal?.aborted) return;
    dispose();
    throw error;
  } finally {
    renderer.debug.onShaderError = previous;
  }
}
