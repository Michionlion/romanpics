import type { MetadataRoute } from 'next';
import { catalog, clusters, collections } from '@/lib/catalog';

export default function sitemap(): MetadataRoute.Sitemap {
  const site = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://romanpics.michionlion.chatgpt.site').replace(/\/$/, '');
  const staticPaths = ['', '/groups', '/collections', '/journey', '/sky', '/status', '/compare/filters', '/compare/field-of-view', '/tools/color', '/about/images'];
  return [
    ...staticPaths.map((path) => ({ url: `${site}${path}`, changeFrequency: 'weekly' as const })),
    ...catalog.map((item) => ({ url: `${site}/images/${item.slug}`, lastModified: item.publishedAt, changeFrequency: 'monthly' as const })),
    ...clusters.map((group) => ({ url: `${site}/groups/${group.slug}`, changeFrequency: 'weekly' as const })),
    ...collections.map((collection) => ({ url: `${site}/collections/${collection.slug}`, lastModified: collection.updatedAt, changeFrequency: 'monthly' as const })),
  ];
}
