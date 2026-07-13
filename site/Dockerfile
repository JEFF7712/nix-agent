FROM node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS builder

WORKDIR /src
COPY site/package.json site/pnpm-lock.yaml site/pnpm-workspace.yaml ./site/
WORKDIR /src/site
RUN corepack enable && pnpm install --frozen-lockfile

WORKDIR /src
COPY site ./site
COPY README.md ./README.md
COPY docs/usage.md docs/agent-install.md docs/privileged-automation.md ./docs/
COPY assets/banner.png ./assets/banner.png

ENV NIX_AGENT_REPO_ROOT=/src
WORKDIR /src/site
RUN pnpm build

FROM nginxinc/nginx-unprivileged:alpine@sha256:592b23aa79a6e6c08ba4b20f1fff700e1328895705966722608e115d62e52d39 AS runtime
COPY --from=builder /src/site/out/ /usr/share/nginx/html/
EXPOSE 8080
