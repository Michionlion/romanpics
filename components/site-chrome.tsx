'use client';

import {
  ChevronDown,
  CircleDot,
  Images,
  Menu,
  Orbit,
  Radio,
  Sparkles,
  Telescope,
  X,
} from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

const primary = [
  { href: '/', label: 'Explore', icon: Images },
  { href: '/groups', label: 'Groups', icon: CircleDot },
  { href: '/sky', label: 'Sky', icon: Sparkles },
  { href: '/journey', label: 'Mission', icon: Telescope },
];

const learn = [
  { href: '/collections', label: 'Collections' },
  { href: '/compare/filters', label: 'Compare filters' },
  { href: '/compare/field-of-view', label: 'Field of view' },
  { href: '/tools/color', label: 'Color composer' },
  { href: '/about/images', label: 'About the images' },
  { href: '/status', label: 'Source status' },
];

function isCurrent(pathname: string, href: string) {
  return href === '/' ? pathname === '/' : pathname.startsWith(href);
}

export function PublicHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  if (pathname.startsWith('/embed/')) return null;

  return (
    <header className="site-header">
      <div className="shell nav-shell">
        <Link className="brand" href="/" aria-label="RomanPics home">
          <span className="brand-mark"><Orbit aria-hidden="true" /></span>
          <span>Roman<span>Pics</span></span>
        </Link>
        <nav className="desktop-nav" aria-label="Primary navigation">
          {primary.map(({ href, label, icon: Icon }) => (
            <Link key={href} className={isCurrent(pathname, href) ? 'active' : ''} href={href}>
              <Icon aria-hidden="true" /> {label}
            </Link>
          ))}
          <details className="nav-more">
            <summary><Sparkles aria-hidden="true" /> Discover <ChevronDown aria-hidden="true" /></summary>
            <div className="nav-popover">
              {learn.map((item) => <Link key={item.href} href={item.href}>{item.label}</Link>)}
            </div>
          </details>
        </nav>
        <Link className="status-pill" href="/status"><Radio aria-hidden="true" /> Sources</Link>
        <button
          className="mobile-menu-button"
          type="button"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
      </div>
      {open && (
        <nav className="mobile-nav shell" aria-label="Mobile navigation">
          {[...primary, ...learn].map((item) => (
            <Link key={item.href} href={item.href} onClick={() => setOpen(false)}>{item.label}</Link>
          ))}
        </nav>
      )}
    </header>
  );
}

export function PublicFooter() {
  const pathname = usePathname();
  if (pathname.startsWith('/embed/')) return null;
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <div>
          <Link className="brand" href="/"><span className="brand-mark"><Orbit aria-hidden="true" /></span> Roman<span>Pics</span></Link>
          <p>A friendly discovery layer for public Roman imagery. Originals stay with NASA and its archive partners.</p>
        </div>
        <nav aria-label="Footer navigation">
          <Link href="/about/images">How imagery works</Link>
          <Link href="/status">Source health</Link>
          <Link href="/feed.xml">RSS feed</Link>
          <Link href="/atom.xml">Atom feed</Link>
          <Link href="/embed/gallery?item=simulated-ultra-deep-field">Embed a card</Link>
        </nav>
      </div>
    </footer>
  );
}
