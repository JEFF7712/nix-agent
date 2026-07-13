import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const repoRoot = process.env.NIX_AGENT_REPO_ROOT
  ? path.resolve(process.env.NIX_AGENT_REPO_ROOT)
  : path.resolve(siteRoot, "..");
const src = path.join(repoRoot, "assets/banner.png");
const destDir = path.join(siteRoot, "public");
const dest = path.join(destDir, "banner.png");

if (!existsSync(src)) {
  console.error(`Missing banner source: ${src}`);
  process.exit(1);
}
mkdirSync(destDir, { recursive: true });
copyFileSync(src, dest);
console.log(`Synced ${src} -> ${dest}`);
