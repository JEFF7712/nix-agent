import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DocsArticle } from "../components/DocsArticle";
import { DocsSidebar } from "../components/DocsSidebar";
import { ALL_DOC_PAGES } from "../lib/docsCatalog";

describe("DocsSidebar", () => {
  it("renders a link for every doc page with the correct href", () => {
    render(<DocsSidebar currentHref="/docs" />);

    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("href", "/docs");
    expect(screen.getByRole("link", { name: "Usage" })).toHaveAttribute("href", "/docs/usage");
    expect(screen.getByRole("link", { name: "Agent install" })).toHaveAttribute(
      "href",
      "/docs/agent-install",
    );
    expect(screen.getByRole("link", { name: "Privileged automation" })).toHaveAttribute(
      "href",
      "/docs/privileged-automation",
    );
  });

  it("renders every ALL_DOC_PAGES entry", () => {
    render(<DocsSidebar currentHref="/docs" />);

    for (const page of ALL_DOC_PAGES) {
      expect(screen.getByRole("link", { name: page.title })).toBeInTheDocument();
    }
  });

  it("marks the current page's link as active", () => {
    render(<DocsSidebar currentHref="/docs/usage" />);

    const activeLink = screen.getByRole("link", { name: "Usage" });
    const overviewLink = screen.getByRole("link", { name: "Overview" });

    expect(activeLink).toHaveAttribute("aria-current", "page");
    expect(overviewLink).not.toHaveAttribute("aria-current");
  });
});

describe("DocsArticle", () => {
  const page = {
    slug: "usage",
    href: "/docs/usage",
    title: "Usage",
    sourcePath: "docs/usage.md",
    githubEditUrl: "https://github.com/JEFF7712/nix-agent/edit/main/docs/usage.md",
  };

  it("renders the page title heading", () => {
    render(<DocsArticle page={page} html="<p>Hello docs</p>" />);

    expect(screen.getByRole("heading", { name: "Usage" })).toBeInTheDocument();
  });

  it("renders an Edit on GitHub link that opens in a new tab safely", () => {
    render(<DocsArticle page={page} html="<p>Hello docs</p>" />);

    const editLink = screen.getByRole("link", { name: /edit on github/i });
    expect(editLink).toHaveAttribute("href", page.githubEditUrl);
    expect(editLink).toHaveAttribute("target", "_blank");
    expect(editLink).toHaveAttribute("rel", "noreferrer");
  });

  it("renders the provided html inside the article body", () => {
    render(<DocsArticle page={page} html="<p>Hello docs</p>" />);

    expect(screen.getByText("Hello docs")).toBeInTheDocument();
  });

  it("does not duplicate the heading when the rendered body already starts with an h1", () => {
    render(<DocsArticle page={page} html="<h1>Body title</h1><p>Content</p>" />);

    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent("Body title");
  });

  it("still shows the chrome title when the body has no leading h1", () => {
    render(<DocsArticle page={page} html="<p>Content</p>" />);

    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent("Usage");
  });
});

describe("docs CSS contract", () => {
  it("defines shell, sidebar, and article rules in globals.css", () => {
    const css = readFileSync(`${process.cwd()}/app/globals.css`, "utf8");

    expect(css).toMatch(/\.docs-shell\s*{/);
    expect(css).toMatch(/\.docs-sidebar\s*{/);
    expect(css).toMatch(/\.docs-article\s*{/);
  });
});
