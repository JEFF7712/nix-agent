export const vertexShader = /* glsl */ `
uniform float uTime;
uniform vec2 uPointer;
uniform float uReducedMotion;
uniform float uPointScale;
uniform vec2 uResolution;

attribute float glyph;
attribute float brightness;
attribute float phase;
attribute float baseSize;
attribute float agent;
attribute float eyeLocalY;

varying float vGlyph;
varying float vBrightness;
varying float vDepth;
varying float vScan;
varying float vAgent;
varying float vAgentBright;
varying float vRepel;

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

float agentBlinkAmount(float time, float motionEnabled) {
  float rate = 0.19;
  float epoch = floor(time * rate);
  float cycle = fract(time * rate);
  float openStart = 0.88 + hash11(epoch) * 0.05;
  float x = clamp((cycle - openStart) / max(1e-3, 1.0 - openStart), 0.0, 1.0);
  float primary = blinkShape(x) * step(openStart, cycle);

  float fireDouble = step(0.72, hash11(epoch + 17.0));
  float doubleStart = openStart - 0.07;
  float xDouble = clamp((cycle - doubleStart) / 0.07, 0.0, 1.0);
  float secondary = blinkShape(xDouble) * step(doubleStart, cycle) * step(cycle, openStart + 0.02) * fireDouble;

  return max(primary, secondary) * motionEnabled;
}

void main() {
  float motionEnabled = 1.0 - uReducedMotion;
  float isEye = step(0.75, agent);
  float isPupil = step(1.5, agent);
  float isSclera = isEye * (1.0 - isPupil);
  float isMouth = step(0.25, agent) * (1.0 - isEye);

  float blinkAmt = agentBlinkAmount(uTime, motionEnabled);
  float squash = mix(1.0, 0.18, blinkAmt * blinkAmt);
  vec3 facePosition = position;
  facePosition.y += eyeLocalY * (squash - 1.0) * isEye;

  float xAngle = 0.42 + sin(uTime * 0.19) * 0.10 * motionEnabled;
  float yAngle = -0.32 + sin(uTime * 0.16 + 0.7) * 0.20 * motionEnabled;
  vec3 rotatedPosition = rotationY(yAngle) * rotationX(xAngle) * facePosition;
  float breathing = 1.0 + sin(uTime * 0.42 + phase) * 0.012 * motionEnabled;
  vec3 basePosition = rotatedPosition * breathing;
  vec4 baseViewPosition = modelViewMatrix * vec4(basePosition, 1.0);
  vec4 baseClipPosition = projectionMatrix * baseViewPosition;
  vec2 baseNdc = baseClipPosition.xy / baseClipPosition.w;
  float aspect = uResolution.x / uResolution.y;
  float scanCoord = baseNdc.y * -0.5 + 0.5;
  float scanHead = fract(uTime * 0.16);
  float scanGap = abs(scanCoord - scanHead);
  scanGap = min(scanGap, 1.0 - scanGap);
  float scan = exp(-(scanGap * scanGap) / (0.11 * 0.11)) * 0.45 * motionEnabled;

  vec2 pointerDelta = baseNdc - uPointer;
  float pointerDistance = length(pointerDelta * vec2(aspect, 1.0));
  float repelField = exp(-pointerDistance * pointerDistance / (0.10 * 0.10)) * motionEnabled;
  vec2 repelDir = normalize(pointerDelta + vec2(1e-5, 1e-5));
  float repel = repelField;

  vec3 transformed = basePosition;
  transformed.xy += repelDir * repel * 0.02;

  vec2 gazeTarget = uPointer;
  float gazeInRange = step(max(abs(gazeTarget.x), abs(gazeTarget.y)), 2.0);
  vec2 gaze = clamp(gazeTarget, -1.0, 1.0) * gazeInRange * motionEnabled;
  transformed.xy += gaze * 0.024 * isPupil;

  float lidY = mix(0.055, -0.05, blinkAmt);
  float lidVisible = 1.0 - isEye + isEye * smoothstep(lidY + 0.006, lidY - 0.004, eyeLocalY);

  vec4 viewPosition = modelViewMatrix * vec4(transformed, 1.0);
  gl_Position = projectionMatrix * viewPosition;
  gl_PointSize = baseSize * uPointScale * (2.25 / max(0.5, -viewPosition.z)) * lidVisible;
  vGlyph = glyph;
  vBrightness = brightness;
  vDepth = clamp(transformed.z * 4.0 + 0.5, 0.0, 1.0);
  vScan = scan;
  vAgent = agent;
  vAgentBright = (isPupil * 1.25 + isSclera * 0.4) * mix(1.0, 0.9, blinkAmt) * lidVisible + isMouth * 0.42;
  vRepel = repel;
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
  float energy = 1.0 + vScan + vRepel * 0.15;
  gl_FragColor = vec4(nixBlue * lit * energy, alpha);
}
`;
