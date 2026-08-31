import { catalog } from '@/lib/catalog';

const site = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://romanpics.michionlion.chatgpt.site').replace(/\/$/, '');
const escapeXml = (value: string) => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');

export function GET() {
  const entries = [...catalog].sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt)).map((item) => `<item><title>${escapeXml(item.title)}</title><link>${site}/images/${item.slug}</link><guid isPermaLink="true">${site}/images/${item.slug}</guid><pubDate>${new Date(item.publishedAt).toUTCString()}</pubDate><description>${escapeXml(`${item.contentLabel}: ${item.summary}`)}</description><enclosure url="${escapeXml(item.thumbnail)}" type="${item.preview?.mediaType ?? 'image/jpeg'}" /></item>`).join('');
  const xml = `<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>RomanPics</title><link>${site}</link><description>New public imagery related to NASA’s Nancy Grace Roman Space Telescope.</description><language>en-us</language><lastBuildDate>${new Date().toUTCString()}</lastBuildDate>${entries}</channel></rss>`;
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml; charset=utf-8', 'Cache-Control': 'public, max-age=900' } });
}
