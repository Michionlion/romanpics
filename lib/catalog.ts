import catalogManifest from '@/data/catalog.json';

export type ContentClass = 'mission-photo' | 'simulation' | 'telescope' | 'visualization' | 'flight-science';
export type ArchiveProduct = { id: string; label: string; kind: string; mediaType: string; dataLevel?: string; url: string; note: string };
export type ProvenanceEvent = { label: string; detail: string; date?: string };
export type CatalogItem = {
  id: string; slug: string; title: string; eyebrow: string; summary: string;
  contentClass: ContentClass; contentLabel: string; isFlightData: boolean;
  publishedAt: string; observedAt?: string; image: string; thumbnail: string;
  originalUrl: string; sourceUrl: string; sourceName: string; sourceAdapter?: string;
  externalId?: string; credit: string; rights: string; rightsUrl?: string; alt: string;
  tags: string[]; votes: number; trendingScore: number; target?: string; instrument?: string;
  viewerHasVoted?: boolean;
  survey?: string; opticalElements?: string[]; coordinates?: { ra: number; dec: number };
  preview?: { url: string; width?: number; height?: number; mediaType: string; provider: string; siteGenerated: boolean };
  clusterSlugs: string[]; relatedSlugs: string[]; products: ArchiveProduct[]; provenance: ProvenanceEvent[];
};
export type Cluster = { id: string; slug: string; title: string; summary: string; rationale: string; votes: number; trendingScore: number; algorithmVersion: string; memberSlugs: string[]; representativeSlug: string; tags: string[]; representative?: CatalogItem; itemCount?: number; viewerHasVoted?: boolean };
export type Collection = { slug: string; title: string; kicker: string; summary: string; description: string; itemSlugs: string[]; updatedAt: string; itemCount?: number };
export type SourceStatus = { id: string; name: string; purpose: string; canonicalUrl: string; state: 'healthy' | 'planned' | 'review'; statusLabel: string; lastSuccessAt?: string; records: number; cadence: string; note: string };
export type JourneyMilestone = { id: string; label: string; date: string; state: 'complete' | 'current' | 'future'; title: string; description: string; href?: string };

const allowedClasses = new Set<ContentClass>(['mission-photo', 'simulation', 'telescope', 'visualization', 'flight-science']);
function validateCatalog(value: unknown): CatalogItem[] {
  if (!Array.isArray(value)) throw new Error('Catalog manifest items must be an array');
  const slugs = new Set<string>();
  return value.map((record, index) => {
    if (!record || typeof record !== 'object') throw new Error(`Catalog item ${index} is not an object`);
    const item = record as Partial<CatalogItem>;
    const required: Array<keyof CatalogItem> = ['id', 'slug', 'title', 'summary', 'contentClass', 'contentLabel', 'publishedAt', 'image', 'thumbnail', 'originalUrl', 'sourceUrl', 'sourceName', 'sourceAdapter', 'externalId', 'credit', 'rights', 'alt'];
    for (const field of required) if (typeof item[field] !== 'string' || !item[field]) throw new Error(`Catalog item ${index} is missing ${field}`);
    if (!allowedClasses.has(item.contentClass as ContentClass)) throw new Error(`Catalog item ${item.slug} has an unknown contentClass`);
    if (slugs.has(item.slug!)) throw new Error(`Duplicate catalog slug: ${item.slug}`);
    slugs.add(item.slug!);
    if (!Array.isArray(item.products) || !Array.isArray(item.provenance)) throw new Error(`Catalog item ${item.slug} needs products and provenance`);
    if (!Array.isArray(item.tags) || !Array.isArray(item.clusterSlugs) || !Array.isArray(item.relatedSlugs)) throw new Error(`Catalog item ${item.slug} needs relationship arrays`);
    return item as CatalogItem;
  });
}

function validateGraph<T extends { slug: string }>(
  value: unknown,
  name: string,
  relationshipField: 'memberSlugs' | 'itemSlugs',
): T[] {
  if (!Array.isArray(value)) throw new Error(`Catalog manifest ${name} must be an array`);
  const slugs = new Set<string>();
  return value.map((record, index) => {
    if (!record || typeof record !== 'object') throw new Error(`${name} ${index} is not an object`);
    const entry = record as T & Record<string, unknown>;
    if (typeof entry.slug !== 'string' || !entry.slug) throw new Error(`${name} ${index} is missing slug`);
    if (slugs.has(entry.slug)) throw new Error(`Duplicate ${name} slug: ${entry.slug}`);
    slugs.add(entry.slug);
    const relationships = entry[relationshipField];
    if (!Array.isArray(relationships)) throw new Error(`${name} ${entry.slug} needs ${relationshipField}`);
    for (const itemSlug of relationships) {
      if (typeof itemSlug !== 'string' || !catalog.some((item) => item.slug === itemSlug)) {
        throw new Error(`${name} ${entry.slug} refers to unknown item ${String(itemSlug)}`);
      }
    }
    return entry;
  });
}

// Canonical portable seed: a backend seeder and the no-API frontend import the
// same JSON. Validation fails fast if identity, provenance, or source links vanish.
export const catalog = validateCatalog(catalogManifest.items);
export const catalogSchemaVersion = catalogManifest.schemaVersion;
export const clusters = validateGraph<Cluster>(catalogManifest.clusters, 'clusters', 'memberSlugs');
export const collections = validateGraph<Collection>(catalogManifest.collections, 'collections', 'itemSlugs');

export const sourceStatuses = [
  { id: 'nasa-images', name: 'NASA Image and Video Library', purpose: 'Mission photography and public media', canonicalUrl: 'https://images.nasa.gov', state: 'healthy', statusLabel: 'Fixture adapter ready', lastSuccessAt: '2026-08-30T18:42:00Z', records: 1, cadence: 'Every 6 hours in production', note: 'Prototype status is generated from the checked-in fixture catalog.' },
  { id: 'nasa-svs', name: 'NASA Scientific Visualization Studio', purpose: 'Visualizations, simulations, and mission media', canonicalUrl: 'https://svs.gsfc.nasa.gov', state: 'healthy', statusLabel: 'Fixture adapter ready', lastSuccessAt: '2026-08-30T18:43:00Z', records: 7, cadence: 'Every 6 hours in production', note: 'Prototype status is generated from the checked-in fixture catalog.' },
  { id: 'ipac', name: 'IPAC / IRSA Roman resources', purpose: 'Reviewed simulation manifests', canonicalUrl: 'https://irsa.ipac.caltech.edu/Missions/roman.html', state: 'review', statusLabel: 'Manifest review planned', records: 0, cadence: 'Reviewed releases', note: 'Only reviewed records should enter the public gallery.' },
  { id: 'mast-roman', name: 'MAST Roman archive', purpose: 'Future WFI science products and previews', canonicalUrl: 'https://archive.stsci.edu/missions-and-data/roman', state: 'planned', statusLabel: 'Waiting for public science products', records: 0, cadence: 'Prompt after science operations begin', note: 'The adapter contract can be tested now against recorded and synthetic responses.' },
] satisfies SourceStatus[];

export const journey = [
  { id: 'build', label: 'Preparation', date: 'Completed', state: 'complete', title: 'Built and tested on Earth', description: 'Teams integrated Roman, deployed its major structures, and prepared the observatory for flight.', href: '/collections/building-roman' },
  { id: 'launch', label: 'Launch', date: 'Aug 30, 2026', state: 'complete', title: 'Roman leaves Earth', description: 'The launch begins Roman’s journey toward its observing orbit around the Sun–Earth L2 region.', href: '/images/launch-day' },
  { id: 'cruise', label: 'Cruise', date: 'Launch era', state: 'current', title: 'Travel and commissioning', description: 'Mission teams check systems and prepare the observatory. Dates shown here remain editorial until connected to a live status source.', href: '/images/journey-to-l2' },
  { id: 'first-images', label: 'First images', date: 'Expected 2027', state: 'future', title: 'The first public views', description: 'RomanPics will switch on its MAST ingestion path only after public products and supported preview interfaces are verified.' },
  { id: 'science', label: 'Science operations', date: 'Future', state: 'future', title: 'A growing public sky catalog', description: 'New public observations can flow into search, similarity groups, feeds, and collections without copying their originals.' },
] satisfies JourneyMilestone[];

export const contentClassOptions: Array<{ value: ContentClass | 'all'; label: string }> = [
  { value: 'all', label: 'Everything' }, { value: 'mission-photo', label: 'Mission photos' }, { value: 'simulation', label: 'Simulations' }, { value: 'telescope', label: 'The telescope' }, { value: 'visualization', label: 'Visualizations' }, { value: 'flight-science', label: 'Flight science' },
];

export function getItem(slug: string) { return catalog.find((item) => item.slug === slug); }
export function getCluster(slug: string) { return clusters.find((group) => group.slug === slug); }
export function getCollection(slug: string) { return collections.find((item) => item.slug === slug); }
export function itemsForSlugs(slugs: string[]) { return slugs.flatMap((slug) => { const item = getItem(slug); return item ? [item] : []; }); }

export type CatalogQuery = { q?: string; contentClass?: string; sort?: 'top' | 'trending' | 'newest' | 'relevance'; page?: number; limit?: number; tag?: string; cursor?: string };
export function queryCatalog(query: CatalogQuery) {
  const needle = query.q?.trim().toLocaleLowerCase() ?? '';
  const contentClass = query.contentClass ?? 'all';
  const page = Math.max(1, query.page ?? 1);
  const limit = Math.min(24, Math.max(1, query.limit ?? 6));
  const sort = query.sort ?? (needle ? 'relevance' : 'newest');
  const matching = catalog.filter((item) => {
    if (contentClass !== 'all' && item.contentClass !== contentClass) return false;
    if (query.tag && !item.tags.includes(query.tag)) return false;
    if (!needle) return true;
    return [item.title, item.eyebrow, item.summary, item.contentLabel, item.credit, item.target ?? '', item.instrument ?? '', item.survey ?? '', ...item.tags].join(' ').toLocaleLowerCase().includes(needle);
  });
  matching.sort((a, b) => {
    if (sort === 'top') return b.votes - a.votes;
    if (sort === 'trending') return b.trendingScore - a.trendingScore;
    if (sort === 'relevance' && needle) { const aTitle = Number(a.title.toLocaleLowerCase().includes(needle)); const bTitle = Number(b.title.toLocaleLowerCase().includes(needle)); if (aTitle !== bTitle) return bTitle - aTitle; }
    return Date.parse(b.publishedAt) - Date.parse(a.publishedAt);
  });
  const start = (page - 1) * limit;
  return { data: matching.slice(start, start + limit), meta: { page, limit, total: matching.length, totalPages: Math.max(1, Math.ceil(matching.length / limit)), sort, mode: 'fixture' as const } };
}
export function catalogFacets(q = '') { const base = queryCatalog({ q, limit: 24 }).data; return contentClassOptions.map((option) => ({ ...option, count: option.value === 'all' ? base.length : base.filter((item) => item.contentClass === option.value).length })); }
export type SurpriseMode = 'anything' | 'galaxies' | 'mission' | 'calm' | 'engineering';
export function surprisePool(mode: SurpriseMode) { if (mode === 'galaxies') return catalog.filter((item) => item.tags.includes('galaxies')); if (mode === 'mission') return catalog.filter((item) => ['mission-photo', 'telescope'].includes(item.contentClass)); if (mode === 'engineering') return catalog.filter((item) => item.contentClass === 'telescope'); if (mode === 'calm') return catalog.filter((item) => ['stars', 'deep field', 'orbit'].some((tag) => item.tags.includes(tag))); return catalog; }
