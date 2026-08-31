import { Search } from 'lucide-react';
import Link from 'next/link';
export default function NotFound() { return <main id="main-content" className="shell not-found"><Search aria-hidden="true" /><p className="kicker">Lost in the wide universe</p><h1>We couldn’t find that page.</h1><p>The catalog may have changed, or the link may be incomplete.</p><Link className="button button-primary" href="/">Explore RomanPics</Link></main>; }
