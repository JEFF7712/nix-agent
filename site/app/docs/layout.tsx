import Link from "next/link";
import type { ReactNode } from "react";
import { DocsSidebarNav } from "../../components/DocsSidebarNav";

export default function DocsLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className="docs-shell">
      <Link className="docs-brand" href="/">
        nix-agent
      </Link>
      <details className="docs-sidebar-toggle">
        <summary>Docs</summary>
        <DocsSidebarNav />
      </details>
      <div className="docs-sidebar-static">
        <DocsSidebarNav />
      </div>
      <main className="docs-content">{children}</main>
    </div>
  );
}
