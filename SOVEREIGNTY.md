# Local application lifecycle

The canonical repository is [Forgejo](https://git.rupan.dev/JEFF7712/nix-agent).
Pull requests and source validation run on the homelab through Woodpecker.
The repository is private. Forgejo requires authenticated access, and CI
checkout uses the dedicated read-only clone account.
The homelab repository owns the application catalog and immutable validation
policy. Repository pipeline files cannot select arbitrary commands or obtain
publishing, signing, promotion, or infrastructure credentials.

The required source check is `ci/woodpecker/application-validation`. Validation
enforces the node-service contract: digest-pinned local upstream base images,
committed pnpm-lock.yaml, and self-contained builds without external cache dependencies.

Production runs the digest-pinned `registry.rupan.dev/apps/nix-agent-site` image from
the homelab's Zot registry. Flux owns deployment configuration under
`gitops/websites/nixagent` in the homelab repository.
