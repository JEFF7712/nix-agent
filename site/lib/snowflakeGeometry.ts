import { GLYPH_CHARACTERS } from "./glyphCharacters";

export interface DensityTier {
  readonly name: "mobile" | "desktop" | "high";
  readonly pointCap: number;
  readonly zDepth: number;
}

export const DENSITY_TIERS = {
  mobile: { name: "mobile", pointCap: 2_400, zDepth: 0.045 },
  desktop: { name: "desktop", pointCap: 6_000, zDepth: 0.06 },
  high: { name: "high", pointCap: 10_000, zDepth: 0.075 },
} as const satisfies Record<string, DensityTier>;

export function selectDensityTier(
  viewportWidth: number,
  deviceMemory?: number,
): DensityTier {
  if (viewportWidth < 768 || (deviceMemory !== undefined && deviceMemory <= 2)) {
    return DENSITY_TIERS.mobile;
  }
  if (viewportWidth < 1_920 || (deviceMemory !== undefined && deviceMemory <= 4)) {
    return DENSITY_TIERS.desktop;
  }
  return DENSITY_TIERS.high;
}

export function snowflakeHorizontalOffset(viewportWidth: number): number {
  return viewportWidth < 768 ? 0 : 0.72;
}

export function seededNoise(x: number, y: number, seed: number): number {
  let value = Math.imul(x | 0, 0x1f123bb5) ^ Math.imul(y | 0, 0x5f356495);
  value ^= Math.imul(seed | 0, 0x6c8e9cf5);
  value ^= value >>> 16;
  value = Math.imul(value, 0x45d9f3b);
  value ^= value >>> 16;
  return (value >>> 0) / 0x100000000;
}

export interface GlyphPointInput {
  readonly alpha: Uint8Array | Uint8ClampedArray;
  readonly width: number;
  readonly height: number;
  readonly tier: DensityTier;
  readonly seed?: number;
  readonly alphaThreshold?: number;
}

export interface GlyphPointData {
  readonly count: number;
  readonly positions: Float32Array;
  readonly glyphIndices: Uint8Array;
  readonly brightness: Float32Array;
  readonly phase: Float32Array;
  readonly baseSize: Float32Array;
}

export interface AgentFaceData extends GlyphPointData {
  readonly agent: Float32Array;
  readonly eyeLocalY: Float32Array;
}

export const AGENT_FLAKE = 0;
export const AGENT_MOUTH = 0.5;
export const AGENT_EYE = 1;
export const AGENT_PUPIL = 2;

// Face geometry in flake-local space (origin = flake center, +y up, extent ~[-1, 1]).
// Tunable: nudge these to reposition the eyes/mouth over the rendered flake.
const EYE_RADIUS = 0.05;
const EYE_Z = 0.06;
const EYE_CENTERS: readonly (readonly [number, number])[] = [
  [-0.15, 0.14],
  [0.15, 0.14],
];
const EYE_STEP = EYE_RADIUS / 11;
const PUPIL_RADIUS = 0.022;
const PUPIL_STEP = PUPIL_RADIUS / 6;
const MOUTH_HALF_WIDTH = 0.13;
const MOUTH_Y = -0.07;
const MOUTH_CURVE = 0.045;
const MOUTH_SAMPLES = 96;

function pushDisc(
  cx: number,
  cy: number,
  radius: number,
  step: number,
  z: number,
  flag: number,
  xs: number[],
  ys: number[],
  zs: number[],
  flags: number[],
  localYs: number[],
) {
  for (let gx = -radius; gx <= radius + 1e-6; gx += step) {
    for (let gy = -radius; gy <= radius + 1e-6; gy += step) {
      if (gx * gx + gy * gy > radius * radius) continue;
      xs.push(cx + gx);
      ys.push(cy + gy);
      zs.push(z);
      flags.push(flag);
      localYs.push(gy);
    }
  }
}

export function buildAgentFacePoints(seed = 0): AgentFaceData {
  const xs: number[] = [];
  const ys: number[] = [];
  const zs: number[] = [];
  const flags: number[] = [];
  const localYs: number[] = [];

  for (const [cx, cy] of EYE_CENTERS) {
    pushDisc(cx, cy, EYE_RADIUS, EYE_STEP, EYE_Z, AGENT_EYE, xs, ys, zs, flags, localYs);
    pushDisc(cx, cy, PUPIL_RADIUS, PUPIL_STEP, EYE_Z + 0.01, AGENT_PUPIL, xs, ys, zs, flags, localYs);
  }

  for (let i = 0; i < MOUTH_SAMPLES; i += 1) {
    const t = (i / (MOUTH_SAMPLES - 1)) * 2 - 1;
    xs.push(t * MOUTH_HALF_WIDTH);
    ys.push(MOUTH_Y + MOUTH_CURVE * t * t);
    zs.push(EYE_Z * 0.8);
    flags.push(AGENT_MOUTH);
    localYs.push(0);
  }

  const count = xs.length;
  const positions = new Float32Array(count * 3);
  const glyphIndices = new Uint8Array(count);
  const brightness = new Float32Array(count);
  const phase = new Float32Array(count);
  const baseSize = new Float32Array(count);
  const agent = new Float32Array(count);
  const eyeLocalY = new Float32Array(count);

  for (let i = 0; i < count; i += 1) {
    const key = Math.round(xs[i] * 1000);
    const keyY = Math.round(ys[i] * 1000);
    positions[i * 3] = xs[i];
    positions[i * 3 + 1] = ys[i];
    positions[i * 3 + 2] = zs[i];
    glyphIndices[i] = Math.floor(seededNoise(key, keyY, seed) * GLYPH_CHARACTERS.length);
    brightness[i] = 1;
    phase[i] = seededNoise(key, keyY, seed + 1) * 2 * Math.PI;
    baseSize[i] = flags[i] === AGENT_PUPIL ? 0.6 : flags[i] === AGENT_EYE ? 0.7 : 0.62;
    agent[i] = flags[i];
    eyeLocalY[i] = localYs[i];
  }

  return { count, positions, glyphIndices, brightness, phase, baseSize, agent, eyeLocalY };
}

export function concatGlyphPointData(flake: GlyphPointData, face: AgentFaceData): AgentFaceData {
  const count = flake.count + face.count;
  const positions = new Float32Array(count * 3);
  const glyphIndices = new Uint8Array(count);
  const brightness = new Float32Array(count);
  const phase = new Float32Array(count);
  const baseSize = new Float32Array(count);
  const agent = new Float32Array(count);
  const eyeLocalY = new Float32Array(count);

  positions.set(flake.positions.subarray(0, flake.count * 3), 0);
  positions.set(face.positions.subarray(0, face.count * 3), flake.count * 3);
  glyphIndices.set(flake.glyphIndices.subarray(0, flake.count), 0);
  glyphIndices.set(face.glyphIndices.subarray(0, face.count), flake.count);
  brightness.set(flake.brightness.subarray(0, flake.count), 0);
  brightness.set(face.brightness.subarray(0, face.count), flake.count);
  phase.set(flake.phase.subarray(0, flake.count), 0);
  phase.set(face.phase.subarray(0, face.count), flake.count);
  baseSize.set(flake.baseSize.subarray(0, flake.count), 0);
  baseSize.set(face.baseSize.subarray(0, face.count), flake.count);
  agent.set(face.agent.subarray(0, face.count), flake.count);
  eyeLocalY.set(face.eyeLocalY.subarray(0, face.count), flake.count);

  return { count, positions, glyphIndices, brightness, phase, baseSize, agent, eyeLocalY };
}

function extrusionSign(centeredX: number, centeredY: number): -1 | 0 | 1 {
  if (centeredY > 0 || (centeredY === 0 && centeredX > 0)) return 1;
  if (centeredY < 0 || centeredX < 0) return -1;
  return 0;
}

export function buildGlyphPointData({
  alpha,
  width,
  height,
  tier,
  seed = 0,
  alphaThreshold = 0,
}: GlyphPointInput): GlyphPointData {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0) {
    throw new RangeError("Mask dimensions must be positive integers");
  }
  if (alpha.length !== width * height) {
    throw new RangeError("Alpha mask length must equal width * height");
  }
  if (!Number.isInteger(tier.pointCap) || tier.pointCap < 0) {
    throw new RangeError("tier.pointCap must be a finite nonnegative integer");
  }
  if (!Number.isFinite(tier.zDepth) || tier.zDepth < 0) {
    throw new RangeError("tier.zDepth must be finite and nonnegative");
  }
  if (!Number.isFinite(alphaThreshold) || alphaThreshold < 0 || alphaThreshold > 255) {
    throw new RangeError("alphaThreshold must be finite and between 0 and 255");
  }
  if (!Number.isInteger(seed)) {
    throw new RangeError("seed must be a finite integer");
  }

  const occupied: number[] = [];
  for (let index = 0; index < alpha.length; index += 1) {
    if (alpha[index] > alphaThreshold) occupied.push(index);
  }

  const count = Math.min(occupied.length, tier.pointCap);
  const positions = new Float32Array(count * 3);
  const glyphIndices = new Uint8Array(count);
  const brightness = new Float32Array(count);
  const phase = new Float32Array(count);
  const baseSize = new Float32Array(count);
  const aspectScale = Math.max(width, height);

  for (let point = 0; point < count; point += 1) {
    const occupiedIndex = count === occupied.length
      ? point
      : Math.round((point * (occupied.length - 1)) / Math.max(count - 1, 1));
    const maskIndex = occupied[occupiedIndex];
    const column = maskIndex % width;
    const row = Math.floor(maskIndex / width);
    const x = ((column + 0.5) - width / 2) * (2 / aspectScale);
    const y = (height / 2 - (row + 0.5)) * (2 / aspectScale);
    const radius = Math.min(1, Math.hypot(x, y));
    const centeredX = column * 2 - (width - 1);
    const centeredY = (height - 1) - row * 2;
    const sign = extrusionSign(centeredX, centeredY);
    const zNoise = seededNoise(Math.abs(centeredX), Math.abs(centeredY), seed + 17) * 2 - 1;
    const z = sign * zNoise * tier.zDepth * (0.25 + radius * 0.75);
    const localNoise = seededNoise(column, row, seed);

    positions[point * 3] = x;
    positions[point * 3 + 1] = y;
    positions[point * 3 + 2] = z;
    glyphIndices[point] = Math.floor(localNoise * GLYPH_CHARACTERS.length);
    brightness[point] = 0.55 + ((alpha[maskIndex] / 255) * 0.45);
    const phaseNoise = seededNoise(column, row, seed + 1) * 2 - 1;
    const sizeNoise = seededNoise(column, row, seed + 2) * 2 - 1;
    phase[point] = (phaseNoise + 1) * Math.PI;
    baseSize[point] = 0.8 + ((sizeNoise + 1) * 0.2);
  }

  return { count, positions, glyphIndices, brightness, phase, baseSize };
}
