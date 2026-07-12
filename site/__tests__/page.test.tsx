import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "../app/page";

describe("Home", () => {
  it("composes the left hero content and reserves the snowflake region", () => {
    const { container } = render(<Home />);

    expect(screen.getByText("nix-agent")).toBeVisible();
    expect(screen.getByText("local MCP server")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "NixOS operations for your AI agent." })).toBeVisible();
    expect(screen.getByText("Evaluate, inspect, validate, format, preview, activate, and roll back your NixOS or Home Manager configuration.")).toBeVisible();
    const installInstruction = screen.getByText("Send this to your coding agent.");

    expect(installInstruction).toBeVisible();
    expect(installInstruction.nextElementSibling).toHaveClass("install-prompt");
    expect(screen.getByRole("textbox", { name: "Install prompt" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Project links" })).toBeVisible();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(container.querySelector("main")).toBeInTheDocument();
    expect(screen.getByTestId("snowflake-region")).toBeInTheDocument();
    expect(container.querySelector("[data-glyph-fallback]")).toBeInTheDocument();
  });

  it("layers the desktop snowflake across the hero and restores mobile flow", () => {
    const css = readFileSync(`${process.cwd()}/app/globals.css`, "utf8");

    expect(css).toMatch(/\.hero\s*{[^}]*position:\s*relative/);
    expect(css).toMatch(/\.hero-copy\s*{[^}]*z-index:\s*1/);
    expect(css).toMatch(/\.snowflake-region\s*{[^}]*position:\s*absolute[^}]*inset:\s*0/);
    expect(css).toMatch(/@media \(max-width: 48rem\)[\s\S]*\.snowflake-region\s*{[^}]*position:\s*relative[^}]*inset:\s*auto/);
  });
});
