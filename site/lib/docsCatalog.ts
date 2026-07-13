export type DocPage = {
  slug: string | null;
  href: string;
  title: string;
  sourcePath: string;
  githubEditUrl: string;
};

const githubEdit = (sourcePath: string) =>
  `https://github.com/JEFF7712/nix-agent/edit/main/${sourcePath}`;

export const OVERVIEW_PAGE: DocPage = {
  slug: null,
  href: "/docs",
  title: "Overview",
  sourcePath: "README.md",
  githubEditUrl: githubEdit("README.md"),
};

export const DOC_PAGES: DocPage[] = [
  {
    slug: "usage",
    href: "/docs/usage",
    title: "Usage",
    sourcePath: "docs/usage.md",
    githubEditUrl: githubEdit("docs/usage.md"),
  },
  {
    slug: "agent-install",
    href: "/docs/agent-install",
    title: "Agent install",
    sourcePath: "docs/agent-install.md",
    githubEditUrl: githubEdit("docs/agent-install.md"),
  },
  {
    slug: "privileged-automation",
    href: "/docs/privileged-automation",
    title: "Privileged automation",
    sourcePath: "docs/privileged-automation.md",
    githubEditUrl: githubEdit("docs/privileged-automation.md"),
  },
];

export const ALL_DOC_PAGES: DocPage[] = [OVERVIEW_PAGE, ...DOC_PAGES];
