import Link from "next/link";
import type { ReactNode } from "react";
import { DocsSidebarNav } from "../../components/DocsSidebarNav";

export default function DocsLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className="docs-shell">
      <Link className="docs-brand" href="/">
        nix-agent
      </Link>
      <aside className="docs-sidebar-panel">
        <details className="docs-nav-details" open>
          <summary>Docs</summary>
          <DocsSidebarNav />
        </details>
      </aside>
      <main className="docs-content">{children}</main>
    </div>
  );
}
