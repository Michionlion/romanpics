import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowUpRight, Orbit } from 'lucide-react';
import { ContentLabel } from '@/components/content-label';
import { getItem } from '@/lib/catalog';

export const metadata: Metadata = { title: 'RomanPics gallery embed', robots: { index: false, follow: true } };
type SearchParams = Promise<Record<string, string | string[] | undefined>>;
export default async function EmbedGallery({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const requested = Array.isArray(params.item) ? params.item[0] : params.item;
  const item = getItem(requested ?? '') ?? getItem('simulated-ultra-deep-field')!;
  return (
    <main id="main-content" className="embed-page">
      <article className="embed-card">
        <Link className="embed-image" href={`/images/${item.slug}`} target="_blank" rel="noreferrer"><img src={item.thumbnail} alt={item.alt} /><ContentLabel contentClass={item.contentClass} label={item.contentLabel} /></Link>
        <div><p>{item.eyebrow}</p><h1><Link href={`/images/${item.slug}`} target="_blank" rel="noreferrer">{item.title}</Link></h1><span>{item.summary}</span><footer><small>{item.credit}</small><Link href={`/images/${item.slug}`} target="_blank" rel="noreferrer"><Orbit aria-hidden="true" /> RomanPics <ArrowUpRight aria-hidden="true" /></Link></footer></div>
      </article>
    </main>
  );
}
