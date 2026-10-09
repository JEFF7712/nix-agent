FROM registry.rupan.dev/upstream/docker.io/library/node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS builder

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

FROM registry.rupan.dev/upstream/docker.io/nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6 AS runtime
COPY --from=builder /src/site/out/ /usr/share/nginx/html/
EXPOSE 8080
