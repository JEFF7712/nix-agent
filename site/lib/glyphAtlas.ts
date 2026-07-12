import { GLYPH_CHARACTERS } from "./glyphCharacters";

export interface GlyphAtlasOptions {
  readonly cellWidth?: number;
  readonly cellHeight?: number;
  readonly columns?: number;
  readonly fontWeight?: number;
}

export interface GlyphAtlas {
  readonly canvas: HTMLCanvasElement;
  readonly columns: number;
  readonly rows: number;
  readonly cellWidth: number;
  readonly cellHeight: number;
}

function atlasFont(fontFamily: string, cellHeight: number, fontWeight: number): string {
  if (typeof fontFamily !== "string" || fontFamily.trim().length === 0) {
    throw new TypeError("fontFamily must be a nonempty string");
  }
  return `${fontWeight} ${Math.floor(cellHeight * 0.72)}px ${fontFamily}`;
}

function primaryFontFamily(fontFamily: string): string {
  const family = fontFamily.match(/^\s*(?:"[^"]+"|'[^']+'|[^,]+)/)?.[0].trim();
  if (!family) throw new TypeError("fontFamily must contain a loadable family");
  return family;
}

export function createGlyphAtlas(
  fontFamily: string,
  {
    cellWidth = 64,
    cellHeight = 64,
    columns = 4,
    fontWeight = 500,
  }: GlyphAtlasOptions = {},
): GlyphAtlas {
  const font = atlasFont(fontFamily, cellHeight, fontWeight);
  const rows = Math.ceil(GLYPH_CHARACTERS.length / columns);
  const canvas = document.createElement("canvas");
  canvas.width = columns * cellWidth;
  canvas.height = rows * cellHeight;

  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D context is unavailable");

  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#ffffff";
  context.font = font;
  context.textAlign = "center";
  context.textBaseline = "middle";

  for (let index = 0; index < GLYPH_CHARACTERS.length; index += 1) {
    const column = index % columns;
    const row = Math.floor(index / columns);
    context.fillText(
      GLYPH_CHARACTERS[index],
      column * cellWidth + cellWidth / 2,
      row * cellHeight + cellHeight / 2,
    );
  }

  return { canvas, columns, rows, cellWidth, cellHeight };
}

export async function createReadyGlyphAtlas(
  fontFamily: string,
  options: GlyphAtlasOptions = {},
): Promise<GlyphAtlas> {
  const { cellHeight = 64, fontWeight = 500 } = options;
  const font = atlasFont(primaryFontFamily(fontFamily), cellHeight, fontWeight);
  await document.fonts.ready;
  await document.fonts.load(font);
  return createGlyphAtlas(fontFamily, options);
}
