import type { MetadataRoute } from 'next';
export default function robots(): MetadataRoute.Robots {
  const site = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://romanpics.michionlion.chatgpt.site').replace(/\/$/, '');
  return { rules: [{ userAgent: '*', allow: '/', disallow: ['/embed/'] }], sitemap: `${site}/sitemap.xml` };
}
