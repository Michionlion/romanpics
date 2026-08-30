import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'RomanPics — Explore the Roman Space Telescope',
  description:
    'A friendly, community-curated guide to imagery from NASA’s Nancy Grace Roman Space Telescope.',
  openGraph: {
    title: 'RomanPics — Explore the Roman Space Telescope',
    description: 'The wide universe, easy to explore.',
    type: 'website',
    images: [
      {
        url: 'https://raw.githubusercontent.com/Michionlion/romanpics/main/public/og.png',
        width: 1200,
        height: 630,
        alt: 'RomanPics — The wide universe, easy to explore.',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'RomanPics — Explore the Roman Space Telescope',
    description: 'The wide universe, easy to explore.',
    images: [
      'https://raw.githubusercontent.com/Michionlion/romanpics/main/public/og.png',
    ],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
