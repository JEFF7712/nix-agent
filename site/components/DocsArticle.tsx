import type { DocPage } from "../lib/docsCatalog";

export function DocsArticle({ page, html }: { page: DocPage; html: string }) {
  return (
    <article className="docs-article">
      <header className="docs-article-header">
        <h1>{page.title}</h1>
        <a href={page.githubEditUrl} rel="noreferrer" target="_blank">
          Edit on GitHub
        </a>
      </header>
      <div className="docs-article-body" dangerouslySetInnerHTML={{ __html: html }} />
    </article>
  );
}
