import Link from "next/link";
import { ALL_DOC_PAGES } from "../lib/docsCatalog";

export function DocsSidebar({ currentHref }: { currentHref: string }) {
  return (
    <nav aria-label="Docs navigation" className="docs-sidebar">
      <ul>
        {ALL_DOC_PAGES.map((page) => {
          const active = page.href === currentHref;
          return (
            <li key={page.href}>
              <Link aria-current={active ? "page" : undefined} href={page.href}>
                {page.title}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
