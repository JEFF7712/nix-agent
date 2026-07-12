"use client";

import { useRef, useState } from "react";

export const INSTALL_PROMPT =
  "Read https://raw.githubusercontent.com/JEFF7712/nix-agent/main/docs/agent-install.md and follow every step to install nix-agent on this NixOS system, install the companion skill, and register nix-agent in my MCP settings for this machine.";

function copyWithTextarea() {
  const previouslyFocused =
    document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const textarea = document.createElement("textarea");
  textarea.value = INSTALL_PROMPT;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);

  try {
    textarea.select();
    if (!document.execCommand("copy")) {
      throw new Error("Copy command failed");
    }
  } finally {
    textarea.remove();
    if (previouslyFocused?.isConnected) {
      previouslyFocused.focus();
    }
  }
}

export function InstallPrompt() {
  const [announcement, setAnnouncement] = useState({ id: 0, message: "" });
  const announcementId = useRef(0);

  function announce(message: string) {
    announcementId.current += 1;
    setAnnouncement({ id: announcementId.current, message });
  }

  async function copyPrompt() {
    try {
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(INSTALL_PROMPT);
        } catch {
          copyWithTextarea();
        }
      } else {
        copyWithTextarea();
      }
      announce("Install prompt copied.");
    } catch {
      announce("Could not copy install prompt.");
    }
  }

  return (
    <div className="install-prompt">
      <input
        aria-label="Install prompt"
        className="install-prompt-field"
        readOnly
        type="text"
        value={INSTALL_PROMPT}
      />
      <button
        aria-label="Copy install prompt"
        className="copy-button"
        onClick={copyPrompt}
        title="Copy install prompt"
        type="button"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <path d="M8 7V3h13v13h-4v5H3V7h5Zm2 0h7v7h2V5h-9v2Zm5 2H5v10h10V9Z" />
        </svg>
      </button>
      <span
        aria-live="polite"
        className="copy-status"
        key={announcement.id}
        role="status"
      >
        {announcement.message}
      </span>
    </div>
  );
}
