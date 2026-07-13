import { IconLinks } from "../components/IconLinks";
import { GlyphSnowflake } from "../components/GlyphSnowflake";
import { InstallPrompt } from "../components/InstallPrompt";

export default function Home() {
  return (
    <main>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="wordmark">
              <span aria-hidden="true" className="wordmark-prompt">❯</span>
              <span>nix-agent</span>
              <span aria-hidden="true" className="wordmark-caret" />
            </span>
            <span className="wordmark-sub">local MCP server</span>
          </p>
          <div className="hero-introduction">
            <h1 aria-label="NixOS operations for your AI agent." id="hero-title">
              <span>NixOS operations</span>
              <span>for your AI agent.</span>
            </h1>
            <p className="hero-description">
              Evaluate, locate, validate, preview, activate, and roll back your NixOS or Home Manager configuration.
            </p>
          </div>
          <p className="install-instruction">Send this to your coding agent.</p>
          <InstallPrompt />
          <IconLinks />
        </div>
        <div aria-hidden="true" className="snowflake-region" data-testid="snowflake-region">
          <GlyphSnowflake />
        </div>
      </section>
    </main>
  );
}
