'use client';

import {
  ArrowLeft,
  ArrowRight,
  Check,
  Link as LinkIcon,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { CatalogCard } from '@/components/catalog-card';
import { listItems, type ItemPage } from '@/lib/api';
import { catalogFacets, type CatalogQuery } from '@/lib/catalog';

type ExploreState = Required<Pick<CatalogQuery, 'q' | 'contentClass' | 'sort' | 'page'>> & {
  cursor?: string;
};

const emptyPage: ItemPage = {
  data: [],
  meta: { page: 1, limit: 6, total: 0, totalPages: 1, sort: 'newest', mode: 'fixture' },
  transport: 'fixture',
};

export function ExploreClient({ initial, initialPage }: { initial: ExploreState; initialPage: ItemPage }) {
  const [filters, setFilters] = useState(initial);
  const [draftQuery, setDraftQuery] = useState(initial.q);
  const [result, setResult] = useState<ItemPage>(initialPage ?? emptyPage);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [cursorHistory, setCursorHistory] = useState<Array<string | undefined>>([]);
  const initialRender = useRef(true);

  const facets = useMemo(() => catalogFacets(filters.q), [filters.q]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (filters.q) params.set('q', filters.q);
    if (filters.contentClass !== 'all') params.set('type', filters.contentClass);
    if (filters.sort !== 'newest') params.set('sort', filters.sort);
    if (filters.page > 1) params.set('page', String(filters.page));
    if (filters.cursor) params.set('cursor', filters.cursor);
    const url = `${window.location.pathname}${params.size ? `?${params}` : ''}`;
    window.history.replaceState({}, '', url);

    if (initialRender.current) {
      initialRender.current = false;
      return;
    }

    let ignore = false;
    void listItems({
      q: filters.q,
      contentClass: filters.contentClass,
      sort: filters.sort,
      page: filters.page,
      limit: 6,
      cursor: filters.cursor,
    }).then(
      (page) => {
        if (!ignore) {
          setResult(page);
          setLoading(false);
        }
      },
      () => {
        if (!ignore) setLoading(false);
      },
    );
    return () => { ignore = true; };
  }, [filters]);

  function updateFilters(
    update: (current: ExploreState) => ExploreState,
    options: { resetCursorHistory?: boolean } = {},
  ) {
    if (options.resetCursorHistory) setCursorHistory([]);
    setLoading(true);
    setFilters(update);
  }

  function submitSearch(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    updateFilters(
      (current) => ({ ...current, q: draftQuery.trim(), page: 1, cursor: undefined }),
      { resetCursorHistory: true },
    );
  }

  async function copySearch() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  const resultLabel = loading
    ? 'Searching the catalog…'
    : `${result.meta.total} ${result.meta.total === 1 ? 'picture' : 'pictures'}`;

  return (
    <section id="explore" className="explore-section" aria-labelledby="explore-title">
      <div className="section-heading split-heading">
        <div>
          <p className="kicker">Browse the catalog</p>
          <h2 id="explore-title">Find your corner of the universe.</h2>
        </div>
        <button className="button button-quiet" type="button" onClick={copySearch}>
          {copied ? <Check aria-hidden="true" /> : <LinkIcon aria-hidden="true" />}
          {copied ? 'Search link copied' : 'Share this search'}
        </button>
      </div>

      <search>
        <form className="search-bar" onSubmit={submitSearch}>
          <Search aria-hidden="true" />
          <label className="sr-only" htmlFor="catalog-search">Search pictures</label>
          <input
            id="catalog-search"
            value={draftQuery}
            onChange={(event) => setDraftQuery(event.target.value)}
            placeholder="Try “galaxies,” “cleanroom,” or “journey”…"
            autoComplete="off"
          />
          {draftQuery && (
            <button type="button" className="search-clear" onClick={() => { setDraftQuery(''); updateFilters((current) => ({ ...current, q: '', page: 1, cursor: undefined }), { resetCursorHistory: true }); }}>
              Clear
            </button>
          )}
          <button className="button button-primary" type="submit">Search</button>
        </form>
      </search>

      <div className="catalog-toolbar">
        <div className="facet-row" aria-label="Filter by image type">
          {facets.map((facet) => (
            <button
              key={facet.value}
              type="button"
              aria-pressed={filters.contentClass === facet.value}
              className={filters.contentClass === facet.value ? 'facet active' : 'facet'}
              onClick={() => updateFilters((current) => ({ ...current, contentClass: facet.value, page: 1, cursor: undefined }), { resetCursorHistory: true })}
            >
              {facet.label} <span>{facet.count}</span>
            </button>
          ))}
        </div>
        <label className="sort-control">
          <SlidersHorizontal aria-hidden="true" />
          <span className="sr-only">Sort pictures</span>
          <select
            value={filters.sort}
            onChange={(event) => updateFilters((current) => ({ ...current, sort: event.target.value as ExploreState['sort'], page: 1, cursor: undefined }), { resetCursorHistory: true })}
          >
            <option value="newest">Newest</option>
            <option value="top">Top voted</option>
            <option value="trending">Trending</option>
            <option value="relevance">Most relevant</option>
          </select>
        </label>
      </div>

      <div className="results-meta" aria-live="polite">
        <span>{resultLabel}</span>
        <span className={`transport ${result.transport}`}>{result.transport === 'api' ? 'Live API' : 'Local catalog demo'}</span>
      </div>

      {result.data.length ? (
        <div className={`catalog-grid ${loading ? 'loading' : ''}`} aria-busy={loading}>
          {result.data.map((item, index) => <CatalogCard key={item.id} item={item} priority={index < 2} />)}
        </div>
      ) : !loading ? (
        <div className="empty-state">
          <Search aria-hidden="true" />
          <h3>No pictures found yet</h3>
          <p>Try a broader word, or include simulations and visualizations while Roman prepares for science imagery.</p>
          <button className="button button-secondary" type="button" onClick={() => { setDraftQuery(''); updateFilters(() => ({ q: '', contentClass: 'all', sort: 'newest', page: 1, cursor: undefined }), { resetCursorHistory: true }); }}>Clear filters</button>
        </div>
      ) : null}

      <nav className="pagination" aria-label="Catalog pages">
        <button
          className="button button-quiet"
          type="button"
          disabled={filters.page <= 1 || loading}
          onClick={() => {
            if (result.transport === 'api') {
              const previousCursor = cursorHistory.at(-1);
              setCursorHistory((history) => history.slice(0, -1));
              updateFilters((current) => ({ ...current, cursor: previousCursor, page: Math.max(1, current.page - 1) }));
            } else {
              updateFilters((current) => ({ ...current, page: Math.max(1, current.page - 1) }));
            }
          }}
        >
          <ArrowLeft aria-hidden="true" /> Previous
        </button>
        <span>Page <strong>{result.meta.page}</strong> of {result.meta.totalPages}</span>
        <button
          className="button button-quiet"
          type="button"
          disabled={(result.transport === 'api' ? !result.nextCursor : filters.page >= result.meta.totalPages) || loading}
          onClick={() => {
            if (result.transport === 'api' && result.nextCursor) {
              setCursorHistory((history) => [...history, filters.cursor]);
              updateFilters((current) => ({ ...current, cursor: result.nextCursor ?? undefined, page: current.page + 1 }));
            } else {
              updateFilters((current) => ({ ...current, page: current.page + 1 }));
            }
          }}
        >
          Next <ArrowRight aria-hidden="true" />
        </button>
      </nav>
    </section>
  );
}
