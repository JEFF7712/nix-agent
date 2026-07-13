import { existsSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadDocHtml, listDocSlugs, repoRoot } from "../lib/docs";

describe("docs markdown pipeline", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("resolves the repo root above site/", () => {
    const root = repoRoot();
    expect(existsSync(path.join(root, "README.md"))).toBe(true);
    expect(existsSync(path.join(root, "docs/usage.md"))).toBe(true);

    if (!process.env.NIX_AGENT_REPO_ROOT) {
      expect(path.basename(process.cwd())).toBe("site");
      expect(root).toBe(path.resolve(process.cwd(), ".."));
    }
  });

  it("honors NIX_AGENT_REPO_ROOT when set", () => {
    const override = path.resolve(process.cwd(), "..");
    vi.stubEnv("NIX_AGENT_REPO_ROOT", override);
    expect(repoRoot()).toBe(override);
  });

  it("lists only slug pages for static params", () => {
    expect(listDocSlugs()).toEqual(["usage", "agent-install", "privileged-automation"]);
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
