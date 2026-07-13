import { afterEach, describe, expect, it, vi } from "vitest";

import {
  FACE_HAPPY_EVENT,
  WINCE_COOLDOWN,
  WINCE_DURATION,
  advanceWince,
  blinkPhaseShiftForWince,
  blinkRate,
  clickSpamAnger,
  combineFaceAnger,
  faceAngerFromPointer,
  faceCenterNdc,
  findFreePulseSlot,
  flashFaceHappy,
  pulseFaceDistance,
  pulseLifeForScale,
  shouldTriggerWince,
  smoothEmotion,
} from "../lib/faceMood";

describe("faceMood", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("raises anger when the pointer is near the face", () => {
    const near = faceAngerFromPointer({
      pointerX: 0.4,
      pointerY: 0.1,
      faceX: 0.4,
      faceY: 0.1,
      speedNdc: 0,
    });
    const far = faceAngerFromPointer({
      pointerX: -0.8,
      pointerY: -0.8,
      faceX: 0.4,
      faceY: 0.1,
      speedNdc: 4,
    });

    expect(near).toBeGreaterThan(0.4);
    expect(far).toBe(0);
  });

  it("adds anger from fast pointer motion near the face", () => {
    const still = faceAngerFromPointer({
      pointerX: 0.45,
      pointerY: 0.12,
      faceX: 0.4,
      faceY: 0.1,
      speedNdc: 0,
    });
    const fast = faceAngerFromPointer({
      pointerX: 0.45,
      pointerY: 0.12,
      faceX: 0.4,
      faceY: 0.1,
      speedNdc: 4,
    });

    expect(fast).toBeGreaterThan(still);
  });

  it("builds anger from click spam and combines it with pointer anger", () => {
    const now = 10_000;
    expect(clickSpamAnger([now], now)).toBe(0);
    expect(clickSpamAnger([now - 200, now], now)).toBeGreaterThan(0);
    expect(clickSpamAnger([now - 800, now - 600, now - 400, now - 200, now], now)).toBe(1);
    expect(combineFaceAnger(0.2, 0.5)).toBeCloseTo(0.7);
    expect(combineFaceAnger(0.8, 0.8)).toBe(1);
  });

  it("smooths emotion values with faster attack than release", () => {
    const rising = smoothEmotion(0, 1, 1 / 60, 9, 1.8);
    const falling = smoothEmotion(1, 0, 1 / 60, 9, 1.8);
    expect(rising).toBeGreaterThan(0.1);
    expect(falling).toBeGreaterThan(0.95);
    expect(smoothEmotion(0.5, 0.5, 0.1)).toBeCloseTo(0.5);
  });

  it("assigns free pulse slots without overwriting active ones", () => {
    expect(findFreePulseSlot([-1, -1, -1])).toBe(0);
    expect(findFreePulseSlot([0.1, -1, 0.2])).toBe(1);
    expect(findFreePulseSlot([0.1, 0.2, 0.3])).toBe(-1);
    expect(pulseLifeForScale(1)).toBeCloseTo(0.4);
    expect(pulseLifeForScale(6)).toBeGreaterThan(pulseLifeForScale(1));
  });

  it("only arms a near-face multi-click wince when idle", () => {
    expect(pulseFaceDistance(0.4, 0.1, 0.4, 0.1, 1)).toBe(0);
    expect(
      shouldTriggerWince({ pulseScale: 1, distance: 0.1, winceAge: -1, winceCooldown: 0 }),
    ).toBe(false);
    // Second click (1.28) should not wince yet; third (~1.64) should.
    expect(
      shouldTriggerWince({ pulseScale: 1.28, distance: 0.2, winceAge: -1, winceCooldown: 0 }),
    ).toBe(false);
    expect(
      shouldTriggerWince({ pulseScale: 1.64, distance: 0.8, winceAge: -1, winceCooldown: 0 }),
    ).toBe(true);
    expect(
      shouldTriggerWince({ pulseScale: 1.64, distance: 1.2, winceAge: -1, winceCooldown: 0 }),
    ).toBe(false);
    expect(
      shouldTriggerWince({ pulseScale: 1.64, distance: 0.2, winceAge: -1, winceCooldown: 0 }),
    ).toBe(true);
    expect(
      shouldTriggerWince({ pulseScale: 2, distance: 0.2, winceAge: 0.1, winceCooldown: 0 }),
    ).toBe(false);
    expect(
      shouldTriggerWince({ pulseScale: 2, distance: 0.2, winceAge: -1, winceCooldown: 0.2 }),
    ).toBe(false);
  });

  it("plays one wince then enforces a cooldown", () => {
    let age = 0;
    let cooldown = 0;
    ({ age, cooldown } = advanceWince(age, cooldown, WINCE_DURATION));
    expect(age).toBe(-1);
    expect(cooldown).toBeCloseTo(WINCE_COOLDOWN);
    expect(shouldTriggerWince({ pulseScale: 3, distance: 0.1, winceAge: age, winceCooldown: cooldown })).toBe(
      false,
    );
    ({ age, cooldown } = advanceWince(age, cooldown, WINCE_COOLDOWN));
    expect(cooldown).toBe(0);
    expect(shouldTriggerWince({ pulseScale: 3, distance: 0.1, winceAge: age, winceCooldown: cooldown })).toBe(
      true,
    );
  });

  it("phase-shifts idle blinks into early open-eye after a wince", () => {
    const rate = blinkRate(0);
    // Mid-blink region of the settle cycle → jump forward past it.
    const midBlinkTime = (0.95 - rate * WINCE_DURATION) / rate;
    const shift = blinkPhaseShiftForWince(midBlinkTime, 0);
    const settleCycle = (((midBlinkTime + shift + WINCE_DURATION) * rate) % 1 + 1) % 1;
    expect(settleCycle).toBeCloseTo(0.12, 5);
    expect(shift).toBeGreaterThan(0);

    // Already early-open at settle → only a small nudge forward.
    const earlyTime = (0.05 - rate * WINCE_DURATION) / rate;
    const earlyShift = blinkPhaseShiftForWince(earlyTime, 0);
    const earlySettle = (((earlyTime + earlyShift + WINCE_DURATION) * rate) % 1 + 1) % 1;
    expect(earlySettle).toBeCloseTo(0.12, 5);
    expect(earlyShift).toBeLessThan(shift);
  });

  it("centers the face estimate on mobile and shifts it right on desktop", () => {
    expect(faceCenterNdc(390)).toEqual({ x: 0, y: 0.1 });
    expect(faceCenterNdc(1280).x).toBeGreaterThan(0);
  });

  it("dispatches a window event when the face should smile", () => {
    const handler = vi.fn();
    window.addEventListener(FACE_HAPPY_EVENT, handler);
    flashFaceHappy();
    expect(handler).toHaveBeenCalledOnce();
    window.removeEventListener(FACE_HAPPY_EVENT, handler);
  });
});
