import { DocsArticle } from "../../components/DocsArticle";
import { loadDocHtml } from "../../lib/docs";

export default async function DocsIndexPage() {
  const { page, html } = await loadDocHtml(null);
  return <DocsArticle page={page} html={html} />;
}
