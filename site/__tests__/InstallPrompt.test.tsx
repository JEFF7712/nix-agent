import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { INSTALL_PROMPT, InstallPrompt } from "../components/InstallPrompt";

describe("InstallPrompt", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the complete prompt in one readonly field", () => {
    render(<InstallPrompt />);

    const field = screen.getByRole("textbox", { name: "Install prompt" });
    expect(field).toHaveValue(INSTALL_PROMPT);
    expect(field).toHaveAttribute("readonly");
  });

  it("copies the complete prompt and announces success", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    render(<InstallPrompt />);

    const button = screen.getByRole("button", { name: "Copy install prompt" });
    expect(button).toHaveAttribute("title", "Copy install prompt");
    await user.click(button);

    expect(writeText).toHaveBeenCalledWith(INSTALL_PROMPT);
    expect(screen.getByRole("status")).toHaveTextContent("Install prompt copied.");
    expect(screen.getByRole("status")).not.toHaveClass("sr-only");
  });

  it("announces clipboard failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    render(<InstallPrompt />);

    await user.click(screen.getByRole("button", { name: "Copy install prompt" }));

    expect(screen.getByRole("status")).toHaveTextContent("Could not copy install prompt.");
  });

  it("falls back to a temporary textarea when the Clipboard API is unavailable", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand });
    render(<InstallPrompt />);

    await user.click(screen.getByRole("button", { name: "Copy install prompt" }));

    expect(execCommand).toHaveBeenCalledWith("copy");
    expect(document.querySelector("textarea")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Install prompt copied.");
  });

  it("reports failure and removes the fallback textarea when copying fails", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn(() => false),
    });
    render(<InstallPrompt />);

    await user.click(screen.getByRole("button", { name: "Copy install prompt" }));

    expect(document.querySelector("textarea")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Could not copy install prompt.");
  });

  it("restores focus after the textarea fallback", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn(() => true),
    });
    vi.spyOn(HTMLTextAreaElement.prototype, "select").mockImplementation(function (
      this: HTMLTextAreaElement,
    ) {
      this.focus();
    });
    render(<InstallPrompt />);
    const button = screen.getByRole("button", { name: "Copy install prompt" });

    await user.click(button);

    expect(button).toHaveFocus();
  });

  it("creates a fresh live-region message for repeated copies", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    render(<InstallPrompt />);

    await user.click(screen.getByRole("button", { name: "Copy install prompt" }));
    const firstStatus = screen.getByRole("status");
    await user.click(screen.getByRole("button", { name: "Copy install prompt" }));

    expect(screen.getByRole("status")).not.toBe(firstStatus);
  });
});
