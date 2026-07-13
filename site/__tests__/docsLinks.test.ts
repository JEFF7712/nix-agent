import { describe, expect, it } from "vitest";
import { rewriteDocsHref, rewriteDocsSrc } from "../lib/docsLinks";

describe("rewriteDocsHref", () => {
  it("maps published markdown paths to site routes and preserves hashes", () => {
    expect(rewriteDocsHref("docs/usage.md", "README.md")).toBe("/docs/usage");
    expect(rewriteDocsHref("docs/usage.md#install", "README.md")).toBe("/docs/usage#install");
    expect(rewriteDocsHref("agent-install.md", "docs/usage.md")).toBe("/docs/agent-install");
    expect(rewriteDocsHref("privileged-automation.md", "docs/usage.md")).toBe(
      "/docs/privileged-automation",
    );
  });

  it("maps unpublished repo paths to GitHub blob URLs", () => {
    expect(rewriteDocsHref("skills/nix-agent/SKILL.md", "README.md")).toBe(
      "https://github.com/JEFF7712/nix-agent/blob/main/skills/nix-agent/SKILL.md",
    );
  });

  it("leaves absolute and in-page links alone", () => {
    expect(rewriteDocsHref("https://example.com/x", "README.md")).toBe("https://example.com/x");
    expect(rewriteDocsHref("#install", "docs/usage.md")).toBe("#install");
  });
});

describe("rewriteDocsSrc", () => {
  it("maps the README banner to the site public path", () => {
    expect(rewriteDocsSrc("assets/banner.png", "README.md")).toBe("/banner.png");
  });
});
