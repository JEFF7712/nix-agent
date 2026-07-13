import { describe, expect, it } from "vitest";
import { loadDocHtml, repoRoot } from "../lib/docs";

describe("docs markdown pipeline", () => {
  it("resolves the repo root above site/", () => {
    expect(repoRoot().endsWith("nix-agent")).toBe(true);
  });

  it("renders the usage doc heading and rewrites a relative doc link", async () => {
    const { page, html } = await loadDocHtml("usage");
    expect(page.title).toBe("Usage");
    expect(html).toContain("nix-agent usage");
    expect(html).toContain('href="/docs/agent-install"');
  });

  it("renders overview from README and points the banner at /banner.png", async () => {
    const { html } = await loadDocHtml(null);
    expect(html).toContain('src="/banner.png"');
    expect(html).toContain('href="/docs/usage#install"');
  });
});
