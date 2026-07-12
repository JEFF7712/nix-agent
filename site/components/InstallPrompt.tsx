"use client";

import { useEffect, useRef, useState } from "react";
import { flashFaceHappy } from "../lib/faceMood";

export const INSTALL_PROMPT =
  "Read https://raw.githubusercontent.com/JEFF7712/nix-agent/main/docs/agent-install.md and follow every step to install nix-agent on this NixOS system, install the companion skills, and register nix-agent in my MCP settings for this machine.";

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
  const [copied, setCopied] = useState(false);
  const announcementId = useRef(0);
  const copiedTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => () => clearTimeout(copiedTimer.current), []);

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
      flashFaceHappy();
      setCopied(true);
      clearTimeout(copiedTimer.current);
      copiedTimer.current = setTimeout(() => {
        setCopied(false);
        setAnnouncement((prev) => ({ ...prev, message: "" }));
      }, 1800);
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
          {copied ? (
            <path d="M9.55 17.6 4.4 12.45l1.4-1.4 3.75 3.75 8.25-8.25 1.4 1.4z" />
          ) : (
            <path d="M8 7V3h13v13h-4v5H3V7h5Zm2 0h7v7h2V5h-9v2Zm5 2H5v10h10V9Z" />
          )}
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
