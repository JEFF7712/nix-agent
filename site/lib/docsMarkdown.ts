import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkRehype from "remark-rehype";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import rehypeStringify from "rehype-stringify";
import { visit } from "unist-util-visit";
import { rewriteDocsHref, rewriteDocsSrc } from "./docsLinks";

type UnistNode = {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
};

// Rewriting happens once, at the hast level, after `rehype-raw` has turned
// both markdown-native links/images and raw HTML (e.g. the README's
// `<img>` banner) into the same element shape. Rewriting mdast link/image
// nodes too would double-process the ones remark-rehype turns into <a>/<img>
// elements on its own.
function rehypeRewriteDocsLinks(sourcePath: string) {
  return (tree: UnistNode) => {
    visit(tree, "element", (node: UnistNode) => {
      const props = node.properties;
      if (!props) return;
      if (node.tagName === "a" && typeof props.href === "string") {
        props.href = rewriteDocsHref(props.href, sourcePath);
      }
      if (node.tagName === "img" && typeof props.src === "string") {
        props.src = rewriteDocsSrc(props.src, sourcePath);
      }
    });
  };
}

const docsSanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    img: [...(defaultSchema.attributes?.img ?? []), "align", "width", "height"],
    p: [...(defaultSchema.attributes?.p ?? []), "align"],
  },
};

export async function renderMarkdownToHtml(markdown: string, sourcePath: string): Promise<string> {
  const file = await unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeRewriteDocsLinks, sourcePath)
    .use(rehypeSanitize, docsSanitizeSchema)
    .use(rehypeStringify)
    .process(markdown);

  return String(file);
}
