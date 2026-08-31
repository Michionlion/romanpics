import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import { PublicFooter, PublicHeader } from '@/components/site-chrome';
import './globals.css';

const geist = Geist({ variable: '--font-geist', subsets: ['latin'] });
const mono = Geist_Mono({ variable: '--font-mono', subsets: ['latin'] });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'https://romanpics.michionlion.chatgpt.site'),
  title: { default: 'RomanPics — The wide universe, easy to explore', template: '%s · RomanPics' },
  description: 'Find, understand, and share public imagery related to NASA’s Nancy Grace Roman Space Telescope.',
  openGraph: {
    title: 'RomanPics — The wide universe, easy to explore',
    description: 'A friendly, community-curated guide to Roman imagery.',
    type: 'website',
    images: [{ url: '/og.png', alt: 'RomanPics — The wide universe, easy to explore.' }],
  },
  twitter: { card: 'summary_large_image' },
  alternates: { types: { 'application/rss+xml': '/feed.xml', 'application/atom+xml': '/atom.xml' } },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geist.variable} ${mono.variable}`}>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <PublicHeader />
        <div className="ambient" aria-hidden="true" />
        {children}
        <PublicFooter />
      </body>
    </html>
  );
}
