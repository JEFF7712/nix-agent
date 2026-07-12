import { describe, expect, it, vi } from "vitest";

vi.mock("next/font/local", () => ({
  default: () => ({ variable: "mock-font" }),
}));

import { metadata } from "../app/layout";

describe("site metadata", () => {
  it("uses the nix-agent chevron mark as its favicon", () => {
    expect(metadata.icons).toEqual({ icon: "/nix-agent-mark.svg" });
  });
});
