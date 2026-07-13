"use client";

import { usePathname } from "next/navigation";
import { DocsSidebar } from "./DocsSidebar";

export function DocsSidebarNav() {
  const pathname = usePathname();
  return <DocsSidebar currentHref={pathname ?? "/docs"} />;
}
