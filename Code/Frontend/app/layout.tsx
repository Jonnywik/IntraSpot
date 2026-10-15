import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from '@/lib/session';
import { ApplicationShell } from '@/components/application-shell';

export const metadata: Metadata = {
  title: "IntraSpot — Find your people",
  description: "Discover campus events and find your place in the community.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><SessionProvider><ApplicationShell>{children}</ApplicationShell></SessionProvider></body>
    </html>
  );
}
