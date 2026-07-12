export const vertexShader = /* glsl */ `
uniform float uTime;
uniform vec2 uPointer;
uniform float uReducedMotion;
uniform float uPointScale;
uniform vec2 uResolution;
uniform float uAnger;
uniform float uHappy;
uniform float uHappyBlink;
uniform float uSleepy;
uniform float uWake;
uniform float uPointerBlend;
uniform float uWinceAge;
uniform vec2 uPulseOrigins[8];
uniform float uPulseAges[8];
uniform float uPulseScales[8];

attribute float glyph;
attribute float brightness;
attribute float phase;
attribute float baseSize;
attribute float agent;
attribute float eyeLocalX;
attribute float eyeLocalY;

varying float vGlyph;
varying float vBrightness;
varying float vDepth;
varying float vScan;
varying float vAgent;
varying float vAgentBright;
varying float vRepel;
varying float vPulse;

mat3 rotationX(float angle) {
  float c = cos(angle);
  float s = sin(angle);
  return mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c);
}

mat3 rotationY(float angle) {
  float c = cos(angle);
  float s = sin(angle);
  return mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c);
}

float hash11(float n) {
  return fract(sin(n) * 43758.5453123);
}

float blinkShape(float x) {
  float close = smoothstep(0.0, 0.28, x);
  float open = 1.0 - smoothstep(0.42, 1.0, x);
  return min(close, open);
}

float agentBlinkAmount(float time, float sleepy, float motionEnabled) {
  float rate = mix(0.19, 0.08, sleepy);
  float epoch = floor(time * rate);
  float cycle = fract(time * rate);
  float openStart = mix(0.88, 0.78, sleepy) + hash11(epoch) * 0.05;
  float x = clamp((cycle - openStart) / max(1e-3, 1.0 - openStart), 0.0, 1.0);
  float primary = blinkShape(x) * step(openStart, cycle);

  float fireDouble = step(0.72, hash11(epoch + 17.0)) * (1.0 - sleepy);
  float doubleStart = openStart - 0.07;
  float xDouble = clamp((cycle - doubleStart) / 0.07, 0.0, 1.0);
  float secondary = blinkShape(xDouble) * step(doubleStart, cycle) * step(cycle, openStart + 0.02) * fireDouble;

  return max(primary, secondary) * motionEnabled;
}

float happyDoubleBlink(float age, float motionEnabled) {
  if (age < 0.0) return 0.0;
  float first = blinkShape(clamp(age / 0.15, 0.0, 1.0)) * step(age, 0.15);
  float second = blinkShape(clamp((age - 0.2) / 0.17, 0.0, 1.0)) * step(0.2, age) * step(age, 0.4);
  return max(first, second) * motionEnabled;
}

void main() {
  float motionEnabled = (1.0 - uReducedMotion) * clamp(uWake, 0.0, 1.0);
  float sleepy = clamp(uSleepy, 0.0, 1.0) * motionEnabled;
  float isEye = step(0.9, agent) * (1.0 - step(2.5, agent));
  float isPupil = step(1.5, agent) * (1.0 - step(2.5, agent));
  float isSclera = isEye * (1.0 - isPupil);
  float isBrow = step(2.5, agent);
  float isMouth = step(0.25, agent) * (1.0 - step(0.9, agent));
  float isFace = step(0.25, agent);

  float blinkAmt = max(agentBlinkAmount(uTime, sleepy, motionEnabled), happyDoubleBlink(uHappyBlink, motionEnabled));
  blinkAmt = max(blinkAmt, sleepy * 0.28);

  // One-shot flinch driven by JS (refractory so stacked clicks don't chop).
  float aspect = uResolution.x / max(uResolution.y, 1.0);
  vec2 faceNdc = vec2(0.38, 0.1);
  float wince = 0.0;
  if (uWinceAge >= 0.0 && uWinceAge < 0.42) {
    float t = uWinceAge / 0.42;
    wince = smoothstep(0.0, 0.05, t) * (1.0 - smoothstep(0.28, 0.85, t)) * motionEnabled;
  }
  blinkAmt = max(blinkAmt, wince * 0.95);
  float squash = mix(1.0, 0.18, blinkAmt * blinkAmt);

  float pulse = 0.0;
  vec2 pulsePush = vec2(0.0);

  float anger = clamp(uAnger, 0.0, 1.0) * (1.0 - clamp(uHappy, 0.0, 1.0)) * motionEnabled;
  float happy = clamp(uHappy, 0.0, 1.0) * motionEnabled;
  float arcT = eyeLocalX;
  float innerBrow = clamp(mix(arcT, -arcT, step(0.0, position.x)), 0.0, 1.0);
  float outerBrow = clamp(mix(-arcT, arcT, step(0.0, position.x)), 0.0, 1.0);

  vec3 facePosition = position;
  facePosition.y += eyeLocalY * (squash - 1.0) * isEye;
  facePosition.y += isBrow * (
    anger * (-0.028 * innerBrow + 0.01 * outerBrow)
    + happy * (0.028 + 0.018 * (1.0 - arcT * arcT))
    + sleepy * (-0.01 * (1.0 - abs(arcT)))
    + wince * (-0.06 * innerBrow - 0.022 * (1.0 - abs(arcT)))
  );
  facePosition.y += isMouth * (
    anger * (0.045 * (1.0 - arcT * arcT) - 0.012)
    + happy * (-0.042 * (1.0 - arcT * arcT))
    + wince * (0.04 * (1.0 - arcT * arcT) + 0.01)
  );
  // Cheek pinch / eye pull-in so big pulses read as a flinch, not just a blink.
  facePosition.x += isEye * wince * (-0.016 * sign(position.x + 1e-5));
  facePosition.y += isEye * wince * 0.008;

  float pointerBlend = clamp(uPointerBlend, 0.0, 1.0);
  float pointerInRange = step(max(abs(uPointer.x), abs(uPointer.y)), 1.45);
  float pointerLive = pointerInRange * pointerBlend;
  float faceDist = length((uPointer - faceNdc) * vec2(aspect, 1.0));
  float nearFace = pointerLive * (1.0 - smoothstep(0.22, 0.58, faceDist));
  vec2 idleGaze = vec2(
    sin(uTime * 0.22) * 0.28 + sin(uTime * 0.09 + 1.7) * 0.12,
    sin(uTime * 0.17 + 0.8) * 0.18 + sin(uTime * 0.07 + 2.1) * 0.06
  ) * motionEnabled * (1.0 - sleepy * 0.55);
  vec2 pointerGaze = clamp(uPointer, -1.0, 1.0) * motionEnabled;
  // Softly crossfade to idle after the cursor leaves the window.
  vec2 gaze = mix(idleGaze, pointerGaze, pointerBlend);
  float gazeStrength = length(gaze) * (1.0 - blinkAmt);
  vec2 gazeDir = normalize(gaze + vec2(1e-5, 1e-5));
  vec2 eyeLocal = vec2(eyeLocalX, eyeLocalY);
  float along = dot(eyeLocal, gazeDir);
  float perp = dot(eyeLocal, vec2(-gazeDir.y, gazeDir.x));
  float alongScale = mix(1.0, 1.05, gazeStrength * mix(0.55, 1.0, pointerBlend));
  float perpScale = mix(1.0, 0.92, gazeStrength * mix(0.55, 1.0, pointerBlend));
  vec2 interestLocal = gazeDir * along * alongScale + vec2(-gazeDir.y, gazeDir.x) * perp * perpScale;
  facePosition.xy += (interestLocal - eyeLocal) * isSclera;

  float tilt = gaze.x * 0.078 * nearFace * (1.0 - sleepy) * motionEnabled;
  vec2 faceCenter = vec2(0.0, 0.08);
  vec2 faceDelta = facePosition.xy - faceCenter;
  float tiltC = cos(tilt);
  float tiltS = sin(tilt);
  facePosition.xy = faceCenter + vec2(
    tiltC * faceDelta.x - tiltS * faceDelta.y,
    tiltS * faceDelta.x + tiltC * faceDelta.y
  ) * isFace + facePosition.xy * (1.0 - isFace);
  facePosition.xy += vec2(gaze.x, gaze.y) * 0.007 * isFace * nearFace * (1.0 - sleepy) * motionEnabled;

  float xAngle = 0.42 + sin(uTime * 0.19) * 0.10 * motionEnabled;
  float yAngle = -0.32 + sin(uTime * 0.16 + 0.7) * 0.20 * motionEnabled;
  vec3 rotatedPosition = rotationY(yAngle) * rotationX(xAngle) * facePosition;
  float breathing = 1.0 + sin(uTime * 0.42 + phase) * 0.012 * motionEnabled;
  vec3 basePosition = rotatedPosition * breathing;
  vec4 baseViewPosition = modelViewMatrix * vec4(basePosition, 1.0);
  vec4 baseClipPosition = projectionMatrix * baseViewPosition;
  vec2 baseNdc = baseClipPosition.xy / baseClipPosition.w;
  float scanCoord = baseNdc.y * -0.5 + 0.5;
  float scanHead = fract(uTime * 0.16);
  float scanGap = abs(scanCoord - scanHead);
  scanGap = min(scanGap, 1.0 - scanGap);
  float scan = exp(-(scanGap * scanGap) / (0.11 * 0.11)) * 0.45 * motionEnabled;

  vec2 pointerDelta = baseNdc - uPointer;
  float pointerDistance = length(pointerDelta * vec2(aspect, 1.0));
  float repelField = exp(-pointerDistance * pointerDistance / (0.10 * 0.10)) * motionEnabled * pointerLive;
  vec2 repelDir = normalize(pointerDelta + vec2(1e-5, 1e-5));
  float repel = repelField * (1.0 - isFace);

  for (int i = 0; i < 8; i++) {
    float pulseAge = uPulseAges[i];
    float pulseScale = max(uPulseScales[i], 1.0);
    float pulseLife = 0.4 * mix(1.0, 1.35, clamp((pulseScale - 1.0) / 5.0, 0.0, 1.0));
    if (pulseAge >= 0.0 && pulseAge < pulseLife) {
      vec2 pulseOrigin = uPulseOrigins[i];
      float t = pulseAge / pulseLife;
      float radius = pulseAge * 0.7 * pulseScale;
      float pulseDist = length((baseNdc - pulseOrigin) * vec2(aspect, 1.0));
      float ring = abs(pulseDist - radius);
      float ringWidth = 0.03 * mix(1.0, 1.5, clamp((pulseScale - 1.0) / 5.0, 0.0, 1.0));
      float ringWave = exp(-ring * ring / (ringWidth * ringWidth));
      float primary = (1.0 - t) * ringWave;
      float settle = -0.3 * ringWave * sin(clamp((t - 0.45) / 0.55, 0.0, 1.0) * 3.14159) * step(0.45, t);
      float wave = (primary + settle) * motionEnabled;
      vec2 pulseDir = normalize(baseNdc - pulseOrigin + vec2(1e-5, 1e-5));
      float amp = 0.028 * mix(1.0, 1.5, clamp((pulseScale - 1.0) / 5.0, 0.0, 1.0));
      pulse += max(wave, 0.0);
      pulsePush += pulseDir * wave * amp;
    }
  }

  vec3 transformed = basePosition;
  transformed.xy += repelDir * repel * 0.02;
  transformed.xy += pulsePush;
  transformed.xy += gaze * mix(0.032, 0.024, pointerBlend) * isPupil;

  float openLid = mix(0.055, 0.018, sleepy);
  float lidY = mix(openLid, -0.05, blinkAmt);
  float lidVisible = 1.0 - isEye + isEye * smoothstep(lidY + 0.008, lidY - 0.006, eyeLocalY);
  float glint = happy * isPupil * smoothstep(0.012, 0.0, length(eyeLocal - vec2(0.007, 0.009)));
  float sparkle = happy * isPupil * (0.35 + 0.65 * (0.5 + 0.5 * sin(uTime * 16.0 + phase * 8.0)));
  sparkle = max(sparkle, glint * 1.4);

  vec4 viewPosition = modelViewMatrix * vec4(transformed, 1.0);
  gl_Position = projectionMatrix * viewPosition;
  float wakeSize = mix(0.2, 1.0, clamp(uWake, 0.0, 1.0));
  gl_PointSize = baseSize * uPointScale * (2.25 / max(0.5, -viewPosition.z)) * lidVisible * (1.0 + sparkle * 0.4) * wakeSize;
  vGlyph = glyph;
  vBrightness = brightness * mix(0.15, 1.0, clamp(uWake, 0.0, 1.0));
  vDepth = clamp(transformed.z * 4.0 + 0.5, 0.0, 1.0);
  vScan = scan;
  vAgent = agent;
  vAgentBright =
    (isPupil * 1.25 + isSclera * 0.4) * mix(1.0, 0.9, blinkAmt) * lidVisible
    + isPupil * sparkle * 1.1 * lidVisible
    + isBrow * 0.72
    + isMouth * 0.42;
  vRepel = repel;
  vPulse = pulse;
}
`;

export const fragmentShader = /* glsl */ `
uniform sampler2D uAtlas;
uniform vec2 uAtlasGrid;

varying float vGlyph;
varying float vBrightness;
varying float vDepth;
varying float vScan;
varying float vAgent;
varying float vAgentBright;
varying float vRepel;
varying float vPulse;

void main() {
  float column = mod(vGlyph, uAtlasGrid.x);
  float row = floor(vGlyph / uAtlasGrid.x);
  vec2 atlasUv = (vec2(column, uAtlasGrid.y - row - 1.0) + gl_PointCoord) / uAtlasGrid;
  float alpha = texture2D(uAtlas, atlasUv).a;
  if (alpha < 0.08) discard;
  vec3 nixBlue = vec3(0.373, 0.722, 0.949);
  float isAgent = step(0.25, vAgent);
  float depthLight = mix(0.62, 1.08, vDepth);
  float lit = mix(vBrightness * depthLight, vAgentBright, isAgent);
  float energy = 1.0 + vScan + vRepel * 0.15 + vPulse * 0.55;
  gl_FragColor = vec4(nixBlue * lit * energy, alpha);
}
`;
