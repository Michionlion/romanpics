import { ArrowUpRight } from 'lucide-react';
import Link from 'next/link';
import { ContentLabel } from '@/components/content-label';
import { VoteButton } from '@/components/vote-button';
import type { CatalogItem } from '@/lib/catalog';

export function CatalogCard({ item, priority = false }: { item: CatalogItem; priority?: boolean }) {
  return (
    <article className="catalog-card">
      <Link className="card-image-link" href={`/images/${item.slug}`} aria-label={`Explore ${item.title}`}>
        <img
          src={item.thumbnail}
          alt={item.alt}
          loading={priority ? 'eager' : 'lazy'}
          decoding="async"
        />
        <ContentLabel contentClass={item.contentClass} label={item.contentLabel} />
      </Link>
      <div className="card-copy">
        <p className="card-eyebrow">{item.eyebrow}</p>
        <h3><Link href={`/images/${item.slug}`}>{item.title}</Link></h3>
        <p>{item.summary}</p>
        <div className="card-footer">
          <span>{item.credit}</span>
          <div>
        <VoteButton id={item.id} kind="items" initialVotes={item.votes} initialActive={item.viewerHasVoted} compact />
            <a className="icon-link" href={item.sourceUrl} target="_blank" rel="noreferrer" aria-label={`View ${item.title} at ${item.sourceName}`}>
              <ArrowUpRight aria-hidden="true" />
            </a>
          </div>
        </div>
      </div>
    </article>
  );
}
