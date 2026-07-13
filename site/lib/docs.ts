import { readFileSync } from "node:fs";
import path from "node:path";
import { ALL_DOC_PAGES, DOC_PAGES, OVERVIEW_PAGE, type DocPage } from "./docsCatalog";
import { renderMarkdownToHtml } from "./docsMarkdown";

export function repoRoot(): string {
  return process.env.NIX_AGENT_REPO_ROOT
    ? path.resolve(process.env.NIX_AGENT_REPO_ROOT)
    : path.resolve(process.cwd(), "..");
}

export function listDocSlugs(): (string | null)[] {
  return ALL_DOC_PAGES.map((page) => page.slug);
}

function findDocPage(slug: string | null): DocPage {
  if (slug === null) {
    return OVERVIEW_PAGE;
  }
  const page = DOC_PAGES.find((candidate) => candidate.slug === slug);
  if (!page) {
    throw new Error(`Unknown doc slug: ${slug}`);
  }
  return page;
}

export async function loadDocHtml(slug: string | null): Promise<{ page: DocPage; html: string }> {
  const page = findDocPage(slug);
  const absolutePath = path.join(repoRoot(), page.sourcePath);

  let markdown: string;
  try {
    markdown = readFileSync(absolutePath, "utf8");
  } catch {
    throw new Error(`Doc source not found: ${absolutePath}`);
  }

  const html = await renderMarkdownToHtml(markdown, page.sourcePath);
  return { page, html };
}
