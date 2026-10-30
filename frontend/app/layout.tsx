import type { Metadata, Viewport } from "next";
import { Barlow_Semi_Condensed, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import type { ReactNode } from "react";

import { APP_NAME } from "@/lib/constants";

import "./globals.css";

// Signage-style condensed face for headings (it echoes the logo's wide industrial lettering),
// a plain humanist sans for reading, and a mono face for the numbers a planner scans.
const barlow = Barlow_Semi_Condensed({
  variable: "--font-barlow",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});
const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: "Finite-capacity production planning for iron and steel sand-casting foundries.",
  icons: {
    icon: [{ url: "/brand/favicon.ico" }, { url: "/brand/icon-192.png", sizes: "192x192" }],
    apple: "/brand/apple-touch-icon.png",
  },
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f2ee" },
    { media: "(prefers-color-scheme: dark)", color: "#111618" },
  ],
};

// Runs before first paint so the saved (or system) theme never flashes the wrong colours.
const themeScript = `(function(){try{var t=localStorage.getItem("vp-theme");if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}})()`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en-IN"
      suppressHydrationWarning
      className={`${barlow.variable} ${plexSans.variable} ${plexMono.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
