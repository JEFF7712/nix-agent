import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { IconLinks } from "../components/IconLinks";

describe("IconLinks", () => {
  it.each([
    ["GitHub", "https://github.com/JEFF7712/nix-agent"],
    ["Documentation", "https://github.com/JEFF7712/nix-agent/blob/main/docs/usage.md"],
  ])("renders the icon-only %s link", (name, href) => {
    render(<IconLinks />);

    const link = screen.getByRole("link", { name });
    expect(link).toHaveAttribute("href", href);
    expect(link).toHaveAttribute("title", name);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    expect(link).toHaveAttribute("data-tooltip", name);
    expect(link).not.toHaveTextContent(name);
    expect(link.querySelector("svg")).toBeInTheDocument();
  });

  it("provides 44px targets and hover and focus tooltip styles", () => {
    const css = readFileSync(`${process.cwd()}/app/globals.css`, "utf8");

    expect(css).toMatch(/\.icon-links a\s*{[^}]*min-width:\s*2\.75rem[^}]*min-height:\s*2\.75rem/);
    expect(css).toMatch(/\.icon-links a::after\s*{[^}]*content:\s*attr\(data-tooltip\)/);
    expect(css).toMatch(/\.icon-links a:hover::after[\s\S]*\.icon-links a:focus-visible::after/);
  });
});
