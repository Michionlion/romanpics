import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, Clock } from 'lucide-react';
import { CatalogCard } from '@/components/catalog-card';
import { readCollection } from '@/lib/api';
import { collections } from '@/lib/catalog';

type Props = { params: Promise<{ slug: string }> };
export function generateStaticParams() { return collections.map((collection) => ({ slug: collection.slug })); }
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const result = await readCollection((await params).slug);
  return result ? { title: result.collection.title, description: result.collection.summary } : { title: 'Collection not found' };
}
export default async function CollectionPage({ params }: Props) {
  const result = await readCollection((await params).slug);
  if (!result) notFound();
  const { collection, items } = result;
  return (
    <main id="main-content" className="shell detail-main">
      <Link className="back-link" href="/collections"><ArrowLeft aria-hidden="true" /> All collections</Link>
      <header className="collection-header"><p className="kicker">{collection.kicker}</p><h1>{collection.title}</h1><p>{collection.description}</p><small><Clock aria-hidden="true" /> Updated {new Date(collection.updatedAt).toLocaleDateString()} · {items.length} pictures</small></header>
      <ol className="collection-sequence">
        {items.map((item, index) => <li key={item.id}><span>{String(index + 1).padStart(2, '0')}</span><CatalogCard item={item} priority={index === 0} /></li>)}
      </ol>
    </main>
  );
}
