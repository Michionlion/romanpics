import type { CatalogItem, Cluster } from '@/lib/catalog';

const contentClasses = {
  'flight-science': 'FLIGHT_SCIENCE',
  simulation: 'SIMULATION',
  telescope: 'GROUND_TEST',
  'mission-photo': 'MISSION_PHOTO',
  visualization: 'VISUALIZATION',
} as const;

export function toApiItem(item: CatalogItem, detail = false) {
  const base = {
    id: item.id,
    slug: item.slug,
    title: item.title,
    summary: item.summary,
    content_class: contentClasses[item.contentClass],
    is_flight_data: item.isFlightData,
    published_at: item.publishedAt,
    observed_at: item.observedAt ?? null,
    source: {
      provider: item.preview?.provider ?? item.sourceAdapter ?? item.sourceName,
      external_id: item.externalId ?? item.id,
      source_url: item.sourceUrl,
      archive_record_url: item.sourceUrl,
      credit: item.credit,
      rights: item.rights,
      rights_url: item.rightsUrl ?? null,
    },
    preview: {
      url: item.thumbnail,
      width: item.preview?.width ?? 320,
      height: item.preview?.height ?? 180,
      format: item.preview?.mediaType ?? 'image/jpeg',
      provider: item.preview?.provider ?? item.sourceName,
      site_generated: item.preview?.siteGenerated ?? false,
      transformation: null,
    },
    alt_text: item.alt,
    tags: item.tags,
    vote_count: item.votes,
    viewer_has_voted: false,
    cluster_id: item.clusterSlugs[0] ?? null,
  };
  if (!detail) return base;
  return {
    ...base,
    originals: [{
      id: `${item.id}-original`,
      url: item.originalUrl,
      subtype: 'provider_original',
      media_type: item.image.endsWith('.png') ? 'image/png' : 'image/jpeg',
      byte_size: null,
      data_level: null,
      active: true,
      superseded_by: null,
    }, ...item.products.map((product) => ({
      id: product.id,
      url: product.url,
      subtype: product.kind,
      media_type: product.mediaType,
      byte_size: null,
      data_level: product.dataLevel ?? null,
      active: true,
      superseded_by: null,
    }))],
    observation: item.instrument || item.survey || item.target ? {
      observation_id: item.externalId ?? item.id,
      program_id: null,
      survey: item.survey ?? null,
      instrument: item.instrument ?? null,
      mode: null,
      optical_elements: item.opticalElements ?? [],
      target: item.target ?? null,
      ra: item.coordinates?.ra ?? null,
      dec: item.coordinates?.dec ?? null,
      data_level: null,
      release_name: null,
      pipeline_version: null,
    } : null,
    processing_note: null,
    superseded_by: null,
  };
}

export function toApiCluster(group: Cluster, members: CatalogItem[], detail = false) {
  const representative = members.find((item) => item.slug === group.representativeSlug) ?? members[0];
  const base = {
    id: group.id,
    slug: group.slug,
    title: group.title,
    summary: group.summary,
    content_class: representative ? contentClasses[representative.contentClass] : 'VISUALIZATION',
    representative: representative ? toApiItem(representative) : null,
    item_count: members.length,
    vote_count: group.votes,
    viewer_has_voted: false,
    version: group.algorithmVersion,
    archived_at: null,
  };
  return detail ? { ...base, members: members.map((item) => toApiItem(item)), next_cursor: null } : base;
}
