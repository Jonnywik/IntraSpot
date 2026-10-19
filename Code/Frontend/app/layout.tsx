import type { Metadata } from "next";
import { Inter_Tight, Noto_Serif_Georgian } from 'next/font/google';
import "./globals.css";
import "./foundations.css";
import "./mobile.css";
import { SessionProvider } from '@/lib/session';
import { ApplicationShell } from '@/components/application-shell';
import { PreferencesProvider } from '@/lib/preferences';
const interTight = Inter_Tight({subsets:['latin'], display:'swap', variable:'--font-inter-tight'});
const notoSerif = Noto_Serif_Georgian({subsets:['latin'], display:'swap', variable:'--font-noto-serif'});

export const metadata: Metadata = {
  title: "IntraSpot — Find your people",
  description: "Discover campus events and find your place in the community.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${interTight.variable} ${notoSerif.variable}`}>
      <body><SessionProvider><PreferencesProvider><ApplicationShell>{children}</ApplicationShell></PreferencesProvider></SessionProvider></body>
    </html>
  );
}
