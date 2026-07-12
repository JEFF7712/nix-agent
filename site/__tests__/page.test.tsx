import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "../app/page";

describe("Home", () => {
  it("composes the left hero content and reserves the snowflake region", () => {
    const { container } = render(<Home />);

    expect(screen.getByText("nix-agent / local MCP server")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "NixOS operations for your AI agent." })).toBeVisible();
    expect(screen.getByText("Inspect, validate, preview, and switch your NixOS or Home Manager configuration.")).toBeVisible();
    const installInstruction = screen.getByText("send this to your coding agent.");

    expect(installInstruction).toBeVisible();
    expect(installInstruction.nextElementSibling).toHaveClass("install-prompt");
    expect(screen.getByRole("textbox", { name: "Install prompt" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Project links" })).toBeVisible();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(container.querySelector("main")).toBeInTheDocument();
    expect(screen.getByTestId("snowflake-region")).toBeInTheDocument();
    expect(container.querySelector("[data-glyph-fallback]")).toBeInTheDocument();
  });
});
