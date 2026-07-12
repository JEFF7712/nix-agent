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

varying float vGlyph;
varying float vBrightness;
varying float vMutation;
varying float vDepth;

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

float boundedNoise(vec3 point) {
  return sin(dot(point, vec3(12.9898, 78.233, 37.719))) * 0.5;
}

void main() {
  float motionEnabled = 1.0 - uReducedMotion;
  float xAngle = 0.42 + sin(uTime * 0.19) * 0.10 * motionEnabled;
  float yAngle = -0.32 + sin(uTime * 0.16 + 0.7) * 0.20 * motionEnabled;
  vec3 rotatedPosition = rotationY(yAngle) * rotationX(xAngle) * position;
  float breathing = 1.0 + sin(uTime * 0.42 + phase) * 0.012 * motionEnabled;
  vec3 basePosition = rotatedPosition * breathing;
  vec4 baseViewPosition = modelViewMatrix * vec4(basePosition, 1.0);
  vec4 baseClipPosition = projectionMatrix * baseViewPosition;
  vec2 baseNdc = baseClipPosition.xy / baseClipPosition.w;
  float aspect = uResolution.x / uResolution.y;
  float pointerDistance = distance(baseNdc * vec2(aspect, 1.0), uPointer * vec2(aspect, 1.0));
  float mutation = exp(-pointerDistance * pointerDistance * 18.0) * motionEnabled;
  float wave = sin(pointerDistance * 28.0 - uTime * 2.1 + phase) * mutation * 0.035;
  float noise = boundedNoise(vec3(position.xy * 9.0, phase + uTime * 0.12)) * 0.008 * mutation;
  vec3 transformed = basePosition;
  transformed.z += wave + noise;

  vec4 viewPosition = modelViewMatrix * vec4(transformed, 1.0);
  gl_Position = projectionMatrix * viewPosition;
  gl_PointSize = baseSize * uPointScale * (2.25 / max(0.5, -viewPosition.z));
  vGlyph = glyph;
  vBrightness = brightness;
  vMutation = mutation;
  vDepth = clamp(transformed.z * 4.0 + 0.5, 0.0, 1.0);
}
`;

export const fragmentShader = /* glsl */ `
uniform sampler2D uAtlas;
uniform vec2 uAtlasGrid;
uniform float uTime;

varying float vGlyph;
varying float vBrightness;
varying float vMutation;
varying float vDepth;

void main() {
  float atlasSize = uAtlasGrid.x * uAtlasGrid.y;
  float mutationOffset = 1.0 + floor(mod(uTime * 5.0 + vGlyph * 1.618, atlasSize - 1.0));
  float mutationGlyph = mod(vGlyph + mutationOffset, atlasSize);
  float mutationAmount = step(0.45, vMutation);
  float glyphIndex = mix(vGlyph, mutationGlyph, mutationAmount);
  float column = mod(glyphIndex, uAtlasGrid.x);
  float row = floor(glyphIndex / uAtlasGrid.x);
  vec2 atlasUv = (vec2(column, uAtlasGrid.y - row - 1.0) + gl_PointCoord) / uAtlasGrid;
  float alpha = texture2D(uAtlas, atlasUv).a;
  if (alpha < 0.08) discard;
  vec3 nixBlue = vec3(0.373, 0.722, 0.949);
  float depthLight = mix(0.62, 1.08, vDepth);
  float glow = 1.0 + vMutation * 0.42;
  gl_FragColor = vec4(nixBlue * vBrightness * depthLight * glow, alpha);
}
`;
