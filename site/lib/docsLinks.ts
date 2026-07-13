import path from "node:path";
import { ALL_DOC_PAGES } from "./docsCatalog";

const GITHUB_BLOB_BASE = "https://github.com/JEFF7712/nix-agent/blob/main";

function splitHash(value: string): { pathPart: string; hash: string } {
  const hashIndex = value.indexOf("#");
  if (hashIndex === -1) {
    return { pathPart: value, hash: "" };
  }
  return {
    pathPart: value.slice(0, hashIndex),
    hash: value.slice(hashIndex),
  };
}

function resolveRepoRelative(target: string, sourcePath: string): string {
  const sourceDir = path.posix.dirname(sourcePath);
  return path.posix.normalize(path.posix.join(sourceDir, target));
}

function findPublishedPage(repoPath: string) {
  return ALL_DOC_PAGES.find((page) => page.sourcePath === repoPath);
}

function isRepoRelativeFilePath(repoPath: string): boolean {
  return repoPath.includes("/") || repoPath.endsWith(".md");
}

export function rewriteDocsHref(href: string, sourcePath: string): string {
  if (/^https?:\/\//.test(href) || href.startsWith("#")) {
    return href;
  }

  const { pathPart, hash } = splitHash(href);
  const repoPath = resolveRepoRelative(pathPart, sourcePath);

  if (repoPath === "README.md") {
    return `/docs${hash}`;
  }

  const publishedPage = findPublishedPage(repoPath);
  if (publishedPage) {
    return `${publishedPage.href}${hash}`;
  }

  if (isRepoRelativeFilePath(repoPath)) {
    return `${GITHUB_BLOB_BASE}/${repoPath}${hash}`;
  }

  return href;
}

export function rewriteDocsSrc(src: string, sourcePath: string): string {
  if (/^https?:\/\//.test(src) || src.startsWith("#")) {
    return src;
  }

  const repoPath = resolveRepoRelative(src, sourcePath);

  if (repoPath === "assets/banner.png") {
    return "/banner.png";
  }

  if (isRepoRelativeFilePath(repoPath)) {
    return `${GITHUB_BLOB_BASE}/${repoPath}`;
  }

  return src;
}
