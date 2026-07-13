import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { IconLinks } from "../components/IconLinks";

describe("IconLinks", () => {
  it("renders the icon-only GitHub link", () => {
    render(<IconLinks />);

    const link = screen.getByRole("link", { name: "GitHub" });
    expect(link).toHaveAttribute("href", "https://github.com/JEFF7712/nix-agent");
    expect(link).toHaveAttribute("title", "GitHub");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(link).toHaveAttribute("data-tooltip", "GitHub");
    expect(link).not.toHaveTextContent("GitHub");
    expect(link.querySelector("svg")).toBeInTheDocument();
  });

  it("renders the icon-only Documentation link", () => {
    render(<IconLinks />);

    const link = screen.getByRole("link", { name: "Documentation" });
    expect(link).toHaveAttribute("href", "/docs");
    expect(link).toHaveAttribute("title", "Documentation");
    expect(link).not.toHaveAttribute("target");
    expect(link).not.toHaveAttribute("rel");
    expect(link).toHaveAttribute("data-tooltip", "Documentation");
    expect(link).not.toHaveTextContent("Documentation");
    expect(link.querySelector("svg")).toBeInTheDocument();
  });

  it("provides 44px targets and hover and focus tooltip styles", () => {
    const css = readFileSync(`${process.cwd()}/app/globals.css`, "utf8");

    expect(css).toMatch(/\.icon-links a\s*{[^}]*min-width:\s*2\.75rem[^}]*min-height:\s*2\.75rem/);
    expect(css).toMatch(/\.icon-links a::after\s*{[^}]*content:\s*attr\(data-tooltip\)/);
    expect(css).toMatch(/\.icon-links a:hover::after[\s\S]*\.icon-links a:focus-visible::after/);
  });
});
