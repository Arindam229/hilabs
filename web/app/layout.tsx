import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HiLabs Data Quality",
  description: "Local-first healthcare-data workflow skeleton",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
