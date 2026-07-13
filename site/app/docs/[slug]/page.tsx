import { notFound } from "next/navigation";
import { DocsArticle } from "../../../components/DocsArticle";
import { DOC_PAGES } from "../../../lib/docsCatalog";
import { loadDocHtml, listDocSlugs } from "../../../lib/docs";

export function generateStaticParams() {
  return listDocSlugs().map((slug) => ({ slug }));
}

export default async function DocSlugPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  if (!DOC_PAGES.some((p) => p.slug === slug)) notFound();
  const { page, html } = await loadDocHtml(slug);
  return <DocsArticle page={page} html={html} />;
}
