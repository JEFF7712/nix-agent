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
