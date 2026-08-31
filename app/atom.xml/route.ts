import { catalog } from '@/lib/catalog';

const site = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://romanpics.michionlion.chatgpt.site').replace(/\/$/, '');
const escapeXml = (value: string) => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');

export function GET() {
  const updated = [...catalog].sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt))[0]?.publishedAt ?? new Date().toISOString();
  const entries = catalog.map((item) => `<entry><id>${site}/images/${item.slug}</id><title>${escapeXml(item.title)}</title><link href="${site}/images/${item.slug}"/><updated>${item.publishedAt}</updated><summary>${escapeXml(`${item.contentLabel}: ${item.summary}`)}</summary><link rel="enclosure" href="${escapeXml(item.thumbnail)}" type="${item.preview?.mediaType ?? 'image/jpeg'}"/></entry>`).join('');
  const xml = `<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><id>${site}/</id><title>RomanPics</title><link href="${site}/atom.xml" rel="self"/><link href="${site}/"/><updated>${updated}</updated><subtitle>The wide universe, easy to explore.</subtitle>${entries}</feed>`;
  return new Response(xml, { headers: { 'Content-Type': 'application/atom+xml; charset=utf-8', 'Cache-Control': 'public, max-age=900' } });
}
