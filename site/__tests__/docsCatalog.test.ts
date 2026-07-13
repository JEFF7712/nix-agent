import { describe, expect, it } from "vitest";
import { DOC_PAGES, OVERVIEW_PAGE } from "../lib/docsCatalog";

describe("docsCatalog", () => {
  it("publishes overview plus the three public docs in sidebar order", () => {
    expect(OVERVIEW_PAGE).toMatchObject({
      slug: null,
      href: "/docs",
      title: "Overview",
      sourcePath: "README.md",
      githubEditUrl: "https://github.com/JEFF7712/nix-agent/edit/main/README.md",
    });
    expect(DOC_PAGES.map((p) => p.slug)).toEqual([
      "usage",
      "agent-install",
      "privileged-automation",
    ]);
    expect(DOC_PAGES.map((p) => p.sourcePath)).toEqual([
      "docs/usage.md",
      "docs/agent-install.md",
      "docs/privileged-automation.md",
    ]);
    expect(DOC_PAGES.every((p) => p.githubEditUrl.includes("/edit/main/docs/"))).toBe(true);
  });
});
