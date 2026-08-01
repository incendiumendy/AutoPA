import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoPA Live Dashboard",
  description:
    "Lokales Live-Dashboard für FLY-ALPS, LIS2DW und temperaturabhängige Pressure-Advance-Tests.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="de">
      <head>
        {/*
          Reads the live Mainsail primary colour from Moonraker and applies
          it to the --primary variables. Deliberately a plain script rather
          than a module: it must run before paint, must not block rendering
          when Moonraker is unreachable, and the dashboard stays fully
          usable on the RatOS default colour if it never resolves.
        */}
        <script src="/theme.js" defer />
      </head>
      <body>{children}</body>
    </html>
  );
}
