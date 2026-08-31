import {
  catalog,
  clusters,
  collections,
  getCluster,
  getCollection,
  getItem,
  itemsForSlugs,
  queryCatalog,
  sourceStatuses,
  surprisePool,
  type CatalogItem,
  type CatalogQuery,
  type Cluster,
  type Collection,
  type SourceStatus,
  type SurpriseMode,
} from '@/lib/catalog';

export type ItemPage = ReturnType<typeof queryCatalog> & {
  transport: 'api' | 'fixture';
  nextCursor?: string | null;
};

function configuredApiBase() {
  const base =
    typeof window === 'undefined'
      ? (process.env.ROMANPICS_INTERNAL_API_BASE ?? process.env.NEXT_PUBLIC_API_BASE ?? '')
      : (process.env.NEXT_PUBLIC_API_BASE ?? '');
  if (!base) return '';
  if (/^https?:\/\//.test(base)) return base.replace(/\/$/, '');
  if (typeof window !== 'undefined') return base.replace(/\/$/, '');
  const siteOrigin = process.env.NEXT_PUBLIC_SITE_URL;
  return siteOrigin ? new URL(base, siteOrigin).toString().replace(/\/$/, '') : '';
}

function apiUrl(path: string) {
  const base = configuredApiBase();
  if (base.endsWith('/v1') && path.startsWith('/v1/')) return `${base}${path.slice(3)}`;
  return `${base}${path}`;
}

async function readJson<T>(path: string, init?: RequestInit): Promise<T> {
  // An unset base intentionally bypasses HTTP. This makes fixture mode explicit
  // and avoids implying that local/demo votes are server-persisted.
  if (!configuredApiBase()) throw new Error('RomanPics is using local fixture mode');
  const headers = new Headers(init?.headers);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: 'include',
    headers,
  });
  if (!response.ok) throw new Error(`RomanPics API returned ${response.status}`);
  return (await response.json()) as T;
}

type ApiContentClass =
  | 'FLIGHT_SCIENCE'
  | 'SIMULATION'
  | 'GROUND_TEST'
  | 'MISSION_PHOTO'
  | 'VISUALIZATION';

type ApiItem = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  content_class: ApiContentClass;
  is_flight_data: boolean;
  published_at?: string | null;
  observed_at?: string | null;
  source: {
    provider: string;
    external_id: string;
    source_url: string;
    archive_record_url?: string | null;
    credit: string;
    rights?: string | null;
    rights_url?: string | null;
  };
  preview: { url: string };
  alt_text?: string;
  tags?: string[];
  vote_count: number;
  viewer_has_voted?: boolean;
  cluster_id?: string | null;
  originals?: Array<{
    id: string;
    url: string;
    subtype: string;
    media_type: string;
    data_level?: string | null;
  }>;
  observation?: {
    survey?: string | null;
    instrument?: string | null;
    optical_elements?: string[];
    target?: string | null;
    ra?: number | null;
    dec?: number | null;
  } | null;
};

const toApiContentClass: Record<string, ApiContentClass> = {
  'flight-science': 'FLIGHT_SCIENCE',
  simulation: 'SIMULATION',
  telescope: 'GROUND_TEST',
  'mission-photo': 'MISSION_PHOTO',
  visualization: 'VISUALIZATION',
};

const fromApiContentClass = {
  FLIGHT_SCIENCE: { value: 'flight-science', label: 'Flight science' },
  SIMULATION: { value: 'simulation', label: 'Simulation' },
  GROUND_TEST: { value: 'telescope', label: 'Ground test' },
  MISSION_PHOTO: { value: 'mission-photo', label: 'Mission photo' },
  VISUALIZATION: { value: 'visualization', label: 'Visualization' },
} as const;

function normalizeApiItem(item: ApiItem): CatalogItem {
  const classification = fromApiContentClass[item.content_class];
  const publishedAt = item.published_at ?? item.observed_at ?? new Date(0).toISOString();
  return {
    id: item.id,
    slug: item.slug,
    title: item.title,
    eyebrow: item.observed_at
      ? `Observed ${new Date(item.observed_at).toLocaleDateString()}`
      : `Published ${new Date(publishedAt).toLocaleDateString()}`,
    summary: item.summary,
    contentClass: classification.value,
    contentLabel: classification.label,
    isFlightData: item.is_flight_data,
    publishedAt,
    observedAt: item.observed_at ?? undefined,
    image: item.preview.url,
    thumbnail: item.preview.url,
    originalUrl:
      item.originals?.find((product) => product.url)?.url ??
      item.source.archive_record_url ??
      item.source.source_url,
    sourceUrl: item.source.source_url,
    sourceName: item.source.provider.replaceAll('_', ' '),
    credit: item.source.credit,
    rights: item.source.rights ?? 'See the authoritative source for usage terms.',
    rightsUrl: item.source.rights_url ?? undefined,
    alt: item.alt_text ?? item.title,
    tags: item.tags ?? [],
    votes: item.vote_count,
    viewerHasVoted: item.viewer_has_voted ?? false,
    trendingScore: item.vote_count,
    target: item.observation?.target ?? undefined,
    instrument: item.observation?.instrument ?? undefined,
    survey: item.observation?.survey ?? undefined,
    opticalElements: item.observation?.optical_elements,
    coordinates:
      item.observation?.ra != null && item.observation.dec != null
        ? { ra: item.observation.ra, dec: item.observation.dec }
        : undefined,
    clusterSlugs: item.cluster_id ? [item.cluster_id] : [],
    relatedSlugs: [],
    products: (item.originals ?? []).map((product) => ({
      id: product.id,
      label: product.subtype,
      kind: product.subtype,
      mediaType: product.media_type,
      dataLevel: product.data_level ?? undefined,
      url: product.url,
      note: 'Hosted by the authoritative archive.',
    })),
    provenance: [
      { label: 'Published by', detail: item.source.provider.replaceAll('_', ' ') },
      { label: 'External record', detail: item.source.external_id },
      { label: 'Classification', detail: classification.label },
    ],
  };
}

export async function listItems(query: CatalogQuery): Promise<ItemPage> {
  const params = new URLSearchParams();
  if (query.q) params.set('q', query.q);
  if (query.contentClass && query.contentClass !== 'all') {
    params.set('content_class', toApiContentClass[query.contentClass]);
  }
  if (query.sort) params.set('sort', query.sort);
  if (query.cursor) params.set('cursor', query.cursor);
  if (query.limit) params.set('limit', String(query.limit));

  try {
    const page = await readJson<{
      data: ApiItem[];
      total_estimate: number;
      next_cursor?: string | null;
    }>(
      `/v1/items?${params.toString()}`,
    );
    const limit = query.limit ?? 6;
    return {
      data: page.data.map(normalizeApiItem),
      meta: {
        page: query.page ?? 1,
        limit,
        total: page.total_estimate,
        totalPages: Math.max(1, Math.ceil(page.total_estimate / limit)),
        sort: query.sort ?? (query.q ? 'relevance' : 'newest'),
        mode: 'fixture',
      },
      transport: 'api',
      nextCursor: page.next_cursor ?? null,
    };
  } catch {
    return { ...queryCatalog(query), transport: 'fixture' };
  }
}

export async function readItem(slug: string): Promise<CatalogItem | undefined> {
  try {
    return normalizeApiItem(
      await readJson<ApiItem>(`/v1/items/${encodeURIComponent(slug)}`),
    );
  } catch {
    return getItem(slug);
  }
}

export async function listSimilarItems(slug: string, fallbackSlugs: string[] = []) {
  try {
    const response = await readJson<{
      data: Array<{ item: ApiItem; score: number; reasons: string[] }>;
      algorithm_version: string;
    }>(`/v1/items/${encodeURIComponent(slug)}/similar?limit=6`);
    return response.data.map((result) => normalizeApiItem(result.item));
  } catch {
    const fixture = getItem(slug);
    const slugs = fallbackSlugs.length > 0 ? fallbackSlugs : (fixture?.relatedSlugs ?? []);
    return itemsForSlugs(slugs);
  }
}

export async function readItemClusters(item: CatalogItem) {
  const results = await Promise.all(item.clusterSlugs.map((identifier) => readCluster(identifier)));
  return results.flatMap((result) => result ? [result.cluster] : []);
}

export async function listClusters(): Promise<Cluster[]> {
  try {
    const response = await readJson<{ data: Array<{
      id: string;
      slug: string;
      title: string;
      summary: string;
      vote_count: number;
      viewer_has_voted?: boolean;
      item_count: number;
      version: string;
      representative: ApiItem;
    }> }>('/v1/clusters');
    return response.data.map((cluster) => {
      const fixture = getCluster(cluster.slug);
      return {
        id: cluster.id,
        slug: cluster.slug,
        title: cluster.title,
        summary: cluster.summary,
        rationale: fixture?.rationale ?? 'Open this group to see why its members are related.',
        votes: cluster.vote_count,
        viewerHasVoted: cluster.viewer_has_voted ?? false,
        trendingScore: cluster.vote_count,
        algorithmVersion: cluster.version,
        memberSlugs: fixture?.memberSlugs ?? [cluster.representative.slug],
        representativeSlug: cluster.representative.slug,
        representative: normalizeApiItem(cluster.representative),
        itemCount: cluster.item_count,
        tags: fixture?.tags ?? [],
      };
    });
  } catch {
    return clusters;
  }
}

export async function readCluster(slug: string) {
  try {
    const cluster = await readJson<{
      id: string;
      slug: string;
      title: string;
      summary: string;
      vote_count: number;
      viewer_has_voted?: boolean;
      version: string;
      representative: ApiItem;
      members: ApiItem[];
    }>(`/v1/clusters/${encodeURIComponent(slug)}`);
    return {
      cluster: {
        id: cluster.id,
        slug: cluster.slug,
        title: cluster.title,
        summary: cluster.summary,
        rationale: 'Members are grouped using stable observation families, duplicate checks, and explainable similarity signals.',
        votes: cluster.vote_count,
        viewerHasVoted: cluster.viewer_has_voted ?? false,
        trendingScore: cluster.vote_count,
        algorithmVersion: cluster.version,
        memberSlugs: cluster.members.map((item) => item.slug),
        representativeSlug: cluster.representative.slug,
        tags: [],
      },
      items: cluster.members.map(normalizeApiItem),
    };
  } catch {
    const cluster = getCluster(slug);
    return cluster ? { cluster, items: itemsForSlugs(cluster.memberSlugs) } : undefined;
  }
}

export async function listCollections(): Promise<Collection[]> {
  try {
    const result = await readJson<{ data: Array<{ slug: string; title: string; summary: string; item_count?: number; updated_at?: string }> }>('/v1/collections');
    return result.data.map((collection) => {
      const fixture = getCollection(collection.slug);
      return {
        slug: collection.slug,
        title: collection.title,
        kicker: fixture?.kicker ?? 'Curated collection',
        summary: collection.summary,
        description: fixture?.description ?? collection.summary,
        itemSlugs: fixture?.itemSlugs ?? [],
        itemCount: collection.item_count ?? fixture?.itemSlugs.length ?? 0,
        updatedAt: collection.updated_at ?? fixture?.updatedAt ?? new Date().toISOString(),
      };
    });
  } catch {
    return collections;
  }
}

export async function readCollection(slug: string) {
  try {
    const result = await readJson<{
      slug: string;
      title: string;
      summary: string;
      items: ApiItem[];
    }>(`/v1/collections/${encodeURIComponent(slug)}`);
    return {
      collection: {
        slug: result.slug,
        title: result.title,
        kicker: 'Curated collection',
        summary: result.summary,
        description: result.summary,
        itemSlugs: result.items.map((item) => item.slug),
        updatedAt: new Date().toISOString(),
      },
      items: result.items.map(normalizeApiItem),
    };
  } catch {
    const collection = getCollection(slug);
    return collection
      ? { collection, items: itemsForSlugs(collection.itemSlugs) }
      : undefined;
  }
}

export async function readSourceStatus(): Promise<{
  data: SourceStatus[];
  transport: 'api' | 'fixture';
}> {
  try {
    const response = await readJson<{ data: Array<{ adapter: string; state: 'healthy' | 'delayed' | 'degraded'; last_success_at: string | null; public_message: string | null; record_count: number }> }>('/v1/sources/status');
    const data = response.data.map<SourceStatus>((source) => {
      const normalizedId = source.adapter.replaceAll('_', '-');
      const fixture = sourceStatuses.find((candidate) => candidate.id === normalizedId);
      const isStaticCatalog = source.adapter === 'static_catalog';
      return {
        id: normalizedId,
        name: fixture?.name ?? (isStaticCatalog ? 'Curated launch-era catalog' : source.adapter.replaceAll('_', ' ')),
        purpose: fixture?.purpose ?? (isStaticCatalog ? 'Reviewed NASA Images and SVS records' : 'Roman imagery source'),
        canonicalUrl: fixture?.canonicalUrl ?? (isStaticCatalog ? 'https://github.com/Michionlion/romanpics/blob/main/data/catalog.json' : '/about/images'),
        state: source.state === 'healthy' ? 'healthy' : 'review',
        statusLabel: source.state === 'healthy' ? 'Healthy' : source.state,
        lastSuccessAt: source.last_success_at ?? undefined,
        records: source.record_count,
        cadence: fixture?.cadence ?? (isStaticCatalog ? 'Reviewed releases' : 'Managed by the source adapter'),
        note: source.public_message ?? fixture?.note ?? 'No public incident message.',
      };
    });
    return { data, transport: 'api' };
  } catch {
    return { data: sourceStatuses, transport: 'fixture' };
  }
}

export async function getSurprise(mode: SurpriseMode) {
  try {
    const response = await readJson<{ mode: string; item: ApiItem }>(`/v1/surprise?mode=${mode}`);
    return normalizeApiItem(response.item);
  } catch {
    const pool = surprisePool(mode);
    return pool[Math.floor(Math.random() * pool.length)] ?? catalog[0];
  }
}

export async function setVote(
  targetKind: 'items' | 'clusters',
  id: string,
  active: boolean,
) {
  if (configuredApiBase()) {
    const result = await readJson<{ viewer_has_voted: boolean; vote_count: number }>(
      `/v1/me/votes/${targetKind}/${encodeURIComponent(id)}`,
      { method: active ? 'PUT' : 'DELETE' },
    );
    return { active: result.viewer_has_voted, votes: result.vote_count };
  }
  const base =
    targetKind === 'items'
      ? (catalog.find((item) => item.id === id)?.votes ?? 0)
      : (clusters.find((cluster) => cluster.id === id)?.votes ?? 0);
  return { active, votes: base + (active ? 1 : 0) };
}
