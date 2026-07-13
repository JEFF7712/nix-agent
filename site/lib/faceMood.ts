export const FACE_HAPPY_EVENT = "nix-agent-face-happy";
export const PULSE_SLOT_COUNT = 8;

export function flashFaceHappy() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(FACE_HAPPY_EVENT));
}

export function pulseLifeForScale(scale: number) {
  const pulseScale = Math.max(scale, 1);
  return 0.4 * (1 + 0.35 * Math.min(1, (pulseScale - 1) / 5));
}

/** Aspect-corrected NDC distance from a click to the face center. */
export function pulseFaceDistance(
  x: number,
  y: number,
  faceX: number,
  faceY: number,
  aspect: number,
) {
  const dx = (x - faceX) * aspect;
  const dy = y - faceY;
  return Math.hypot(dx, dy);
}

/** True when a stacked pulse (3+ clicks) lands close enough to flinch. */
export function shouldTriggerWince({
  pulseScale,
  distance,
  winceAge,
  winceCooldown,
}: {
  pulseScale: number;
  distance: number;
  winceAge: number;
  winceCooldown: number;
}) {
  // scale 1.28^2 ≈ 1.64 = third rapid click; distance is host-NDC to face (aspect-corrected).
  return pulseScale >= 1.6 && distance < 0.9 && winceAge < 0 && winceCooldown <= 0;
}

export const WINCE_DURATION = 0.42;
export const WINCE_COOLDOWN = 0.55;

/** Idle blink rate matching `agentBlinkAmount` in the vertex shader. */
export function blinkRate(sleepy = 0) {
  return 0.19 * (1 - sleepy) + 0.08 * sleepy;
}

/**
 * Time shift that lands the idle blink cycle in early open-eye after a wince,
 * so the flinch does not collide with an in-flight or imminent blink.
 */
export function blinkPhaseShiftForWince(time: number, sleepy = 0) {
  const rate = blinkRate(sleepy);
  const settleTime = time + WINCE_DURATION;
  const cycle = ((settleTime * rate) % 1 + 1) % 1;
  const target = 0.12;
  const deltaCycle = cycle <= target ? target - cycle : 1 - cycle + target;
  return deltaCycle / rate;
}

/** Advance a one-shot wince; returns next age (-1 when finished) and remaining cooldown. */
export function advanceWince(age: number, cooldown: number, dt: number) {
  let nextAge = age;
  let nextCooldown = Math.max(0, cooldown - dt);
  if (nextAge >= 0) {
    nextAge += dt;
    if (nextAge >= WINCE_DURATION) {
      nextAge = -1;
      nextCooldown = Math.max(nextCooldown, WINCE_COOLDOWN);
    }
  }
  return { age: nextAge, cooldown: nextCooldown };
}

/** Find a free pulse slot, or -1 if every slot is still playing. */
export function findFreePulseSlot(ages: ArrayLike<number>) {
  for (let i = 0; i < ages.length; i += 1) {
    if (ages[i] < 0) return i;
  }
  return -1;
}

/** Map pointer proximity + near-face speed into a 0..1 anger amount. */
export function faceAngerFromPointer({
  pointerX,
  pointerY,
  faceX,
  faceY,
  speedNdc,
}: {
  pointerX: number;
  pointerY: number;
  faceX: number;
  faceY: number;
  speedNdc: number;
}) {
  const dx = pointerX - faceX;
  const dy = pointerY - faceY;
  const distSq = dx * dx + dy * dy;
  const proximity = Math.exp(-distSq / (0.07 * 0.07));
  if (proximity < 0.12) return 0;
  const speed = Math.min(1, Math.max(0, (speedNdc - 0.6) / 3.2));
  return Math.min(1, proximity * (0.55 + 0.45 * speed));
}

/** Anger from rapid click spam in a short window. */
export function clickSpamAnger(clickTimes: readonly number[], now: number, windowMs = 1800) {
  const recent = clickTimes.filter((time) => now - time <= windowMs).length;
  if (recent < 2) return 0;
  return Math.min(1, (recent - 1) / 4);
}

export function combineFaceAnger(pointerAnger: number, spamAnger: number) {
  return Math.min(1, pointerAnger + spamAnger);
}

/** Critically damp emotion values toward a target for smoother face morphs. */
export function smoothEmotion(current: number, target: number, dt: number, attack = 10, release = 2.2) {
  const rate = target > current ? attack : release;
  return current + (target - current) * (1 - Math.exp(-dt * rate));
}

/** Host-NDC estimate of the agent face center for the current layout. */
export function faceCenterNdc(viewportWidth: number) {
  return {
    // Matches the snowflake's projected face in host canvas NDC.
    x: viewportWidth < 768 ? 0 : 0.38,
    y: 0.1,
  };
}
