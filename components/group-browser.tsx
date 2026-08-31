'use client';

import { ArrowRight, Layers3, Search } from 'lucide-react';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { VoteButton } from '@/components/vote-button';
import { getItem, type Cluster } from '@/lib/catalog';

export function GroupBrowser({ groups }: { groups: Cluster[] }) {
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<'top' | 'trending' | 'newest'>('top');
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return groups
      .filter((group) => !needle || [group.title, group.summary, ...group.tags].join(' ').toLowerCase().includes(needle))
      .sort((a, b) => sort === 'trending' ? b.trendingScore - a.trendingScore : sort === 'top' ? b.votes - a.votes : a.title.localeCompare(b.title));
  }, [groups, query, sort]);

  return (
    <section>
      <div className="group-toolbar">
        <label className="mini-search"><Search aria-hidden="true" /><span className="sr-only">Search groups</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search groups…" /></label>
        <label className="sort-control"><span className="sr-only">Sort groups</span><select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="top">Top voted</option><option value="trending">Trending</option><option value="newest">Alphabetical</option></select></label>
      </div>
      <div className="group-list">
        {visible.map((group) => {
          const members = group.memberSlugs.flatMap((slug) => { const item = getItem(slug); return item ? [item] : []; });
          const previews = members.length > 0 ? members : (group.representative ? [group.representative] : []);
          return (
            <article className="group-card" key={group.id}>
              <Link className="group-card-images" href={`/groups/${group.slug}`} aria-label={`Open ${group.title}`}>
                {previews.slice(0, 3).map((item, index) => <img key={item.id} src={item.thumbnail} alt="" style={{ '--position': index } as React.CSSProperties} />)}
                <span><Layers3 aria-hidden="true" /> {group.itemCount ?? members.length}</span>
              </Link>
              <div className="group-card-copy">
                <div><p className="kicker">Similarity neighborhood</p><h2><Link href={`/groups/${group.slug}`}>{group.title}</Link></h2><p>{group.summary}</p></div>
                <div className="tag-row">{group.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
                <footer><VoteButton id={group.id} kind="clusters" initialVotes={group.votes} initialActive={group.viewerHasVoted} /><Link className="text-link" href={`/groups/${group.slug}`}>Explore group <ArrowRight aria-hidden="true" /></Link></footer>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
