import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Caveat, Instrument_Sans, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";

import { ResponsiveTables } from "@/components/ResponsiveTables";
import { Tooltips } from "@/components/Tooltips";
import { APP_NAME } from "@/lib/constants";

import "./globals.css";

// A characterful grotesque for headings and big numbers, a clean sans for reading and a mono face
// for the figures a planner scans down a column.
const bricolage = Bricolage_Grotesque({
  variable: "--font-bricolage",
  subsets: ["latin"],
  display: "swap",
});
const instrument = Instrument_Sans({
  variable: "--font-instrument",
  subsets: ["latin"],
  display: "swap",
});
// A handwriting face, used once: the "Ask AI" note under the assistant button.
const caveat = Caveat({
  variable: "--font-caveat",
  subsets: ["latin"],
  weight: ["600"],
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  display: "swap",
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
    { media: "(prefers-color-scheme: light)", color: "#ece9e2" },
    { media: "(prefers-color-scheme: dark)", color: "#0c1113" },
  ],
};

// Runs before first paint so the saved (or system) theme never flashes the wrong colours.
const themeScript = `(function(){try{var t=localStorage.getItem("vp-theme");if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}})()`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en-IN"
      suppressHydrationWarning
      className={`${bricolage.variable} ${instrument.variable} ${jetbrains.variable} ${caveat.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-dvh">
        {children}
        <Tooltips />
        <ResponsiveTables />
      </body>
    </html>
  );
}
