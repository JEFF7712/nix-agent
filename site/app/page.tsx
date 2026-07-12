import { IconLinks } from "../components/IconLinks";
import { GlyphSnowflake } from "../components/GlyphSnowflake";
import { InstallPrompt } from "../components/InstallPrompt";

export default function Home() {
  return (
    <main>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow">nix-agent / local MCP server</p>
          <div className="hero-introduction">
            <h1 aria-label="NixOS operations for your AI agent." id="hero-title">
              <span>NixOS operations</span>
              <span>for your AI agent.</span>
            </h1>
            <p className="hero-description">
              Inspect, validate, preview, and switch your NixOS or Home Manager configuration.
            </p>
          </div>
          <p className="install-instruction">send this to your coding agent.</p>
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
