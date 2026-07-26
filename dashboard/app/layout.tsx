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
      <body>{children}</body>
    </html>
  );
}
