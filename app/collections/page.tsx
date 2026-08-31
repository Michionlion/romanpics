import type { Metadata } from 'next';
import { ArrowRight, BookOpen } from 'lucide-react';
import Link from 'next/link';
import { PageIntro } from '@/components/page-intro';
import { listCollections } from '@/lib/api';
import { getItem } from '@/lib/catalog';

export const metadata: Metadata = { title: 'Collections', description: 'Friendly, curated paths through Roman’s imagery and mission story.' };

export default async function CollectionsPage() {
  const collections = await listCollections();
  return (
    <main id="main-content" className="shell">
      <PageIntro kicker="Curated paths" title="Stories, not just search results."><p>Collections turn authoritative images into short, approachable journeys. Every picture keeps its original credit, classification, and source.</p></PageIntro>
      <section className="collection-grid">
        {collections.map((collection) => {
          const cover = getItem(collection.itemSlugs[0]);
          return (
            <Link className="collection-card" href={`/collections/${collection.slug}`} key={collection.slug}>
              {cover && <img src={cover.thumbnail} alt="" />}
              <span className="collection-overlay"><span className="collection-icon"><BookOpen aria-hidden="true" /></span><small>{collection.kicker} · {collection.itemCount ?? collection.itemSlugs.length} pictures</small><strong>{collection.title}</strong><span>{collection.summary}</span><b>Open collection <ArrowRight aria-hidden="true" /></b></span>
            </Link>
          );
        })}
      </section>
    </main>
  );
}
