import type { DocPage } from "../lib/docsCatalog";

const BODY_HAS_H1 = /^\s*<h1[\s>]/i;

export function DocsArticle({ page, html }: { page: DocPage; html: string }) {
  const bodyHasOwnTitle = BODY_HAS_H1.test(html);

  return (
    <article className="docs-article">
      <header className="docs-article-header">
        {bodyHasOwnTitle ? null : <h1>{page.title}</h1>}
        <a href={page.githubEditUrl} rel="noreferrer" target="_blank">
          Edit on GitHub
        </a>
      </header>
      <div className="docs-article-body" dangerouslySetInnerHTML={{ __html: html }} />
    </article>
  );
}
