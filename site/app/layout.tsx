import type { Metadata } from "next";
import Script from "next/script";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import "./globals.css";

const mono = localFont({
  src: [
    {
      path: "./fonts/ibm-plex-mono-latin-400-normal.woff2",
      weight: "400",
      style: "normal",
    },
    {
      path: "./fonts/ibm-plex-mono-latin-500-normal.woff2",
      weight: "500",
      style: "normal",
    },
  ],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "nix-agent",
  description: "NixOS operations for your AI agent.",
  icons: { icon: "/nix-agent-mark.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className={mono.variable}>
      <body>
        {children}
        <Script src="https://tally.rupan.dev/t.js" data-website-id="e8777c6b-0876-4b6e-8495-3bfee147cf8a" data-domains="nix-agent.rupan.dev" strategy="afterInteractive" />
      </body>
    </html>
  );
}
