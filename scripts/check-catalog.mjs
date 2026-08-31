import { readFile } from 'node:fs/promises';

const manifestUrl = new URL('../data/catalog.json', import.meta.url);
const linkMode = process.argv.includes('--links');
const allowedImageHosts = new Set([
  'images-assets.nasa.gov',
  'svs.gsfc.nasa.gov',
]);
const allowedSourceHosts = new Set([
  'archive.stsci.edu',
  'images.nasa.gov',
  'irsa.ipac.caltech.edu',
  'roman.ipac.caltech.edu',
  'svs.gsfc.nasa.gov',
  'www.nasa.gov',
]);
const contentClasses = new Set([
  'flight-science',
  'mission-photo',
  'simulation',
  'telescope',
  'visualization',
]);

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

function parseHttps(value, label) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${label} is not a URL`);
  }
  invariant(url.protocol === 'https:', `${label} must use HTTPS`);
  invariant(!url.username && !url.password, `${label} must not contain credentials`);
  invariant(!url.hash, `${label} must not contain a fragment`);
  return url;
}

function checkItem(item, seenIds, seenSlugs) {
  const at = `item ${JSON.stringify(item?.slug ?? item?.id ?? '<unknown>')}`;
  invariant(item && typeof item === 'object', `${at} must be an object`);
  for (const field of [
    'id',
    'slug',
    'title',
    'summary',
    'contentClass',
    'contentLabel',
    'publishedAt',
    'thumbnail',
    'image',
    'originalUrl',
    'sourceUrl',
    'sourceName',
    'credit',
    'rights',
    'alt',
  ]) {
    invariant(typeof item[field] === 'string' && item[field].trim(), `${at}.${field} is required`);
  }
  invariant(!seenIds.has(item.id), `${at} duplicates id ${item.id}`);
  invariant(!seenSlugs.has(item.slug), `${at} duplicates slug ${item.slug}`);
  seenIds.add(item.id);
  seenSlugs.add(item.slug);
  invariant(/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(item.slug), `${at}.slug is not URL-safe`);
  invariant(contentClasses.has(item.contentClass), `${at}.contentClass is invalid`);
  invariant(
    item.isFlightData === (item.contentClass === 'flight-science'),
    `${at}.isFlightData must match flight-science exactly`,
  );
  invariant(item.alt.length >= 24, `${at}.alt is too short to be descriptive`);
  invariant(Array.isArray(item.tags) && item.tags.length > 0, `${at}.tags are required`);
  invariant(Array.isArray(item.products) && item.products.length > 0, `${at}.products are required`);
  invariant(Array.isArray(item.provenance) && item.provenance.length > 0, `${at}.provenance is required`);
  invariant(Number.isFinite(Date.parse(item.publishedAt)), `${at}.publishedAt is invalid`);

  for (const field of ['thumbnail', 'image', 'originalUrl']) {
    const url = parseHttps(item[field], `${at}.${field}`);
    invariant(allowedImageHosts.has(url.hostname), `${at}.${field} host is not reviewed`);
  }
  const sourceUrl = parseHttps(item.sourceUrl, `${at}.sourceUrl`);
  invariant(allowedSourceHosts.has(sourceUrl.hostname), `${at}.sourceUrl host is not reviewed`);
  if (item.rightsUrl) {
    const rightsUrl = parseHttps(item.rightsUrl, `${at}.rightsUrl`);
    invariant(allowedSourceHosts.has(rightsUrl.hostname), `${at}.rightsUrl host is not reviewed`);
  }
  for (const [index, product] of item.products.entries()) {
    invariant(product && typeof product === 'object', `${at}.products[${index}] must be an object`);
    invariant(product.id && product.label && product.mediaType && product.note, `${at}.products[${index}] is incomplete`);
    const url = parseHttps(product.url, `${at}.products[${index}].url`);
    invariant(
      allowedImageHosts.has(url.hostname) || allowedSourceHosts.has(url.hostname),
      `${at}.products[${index}].url host is not reviewed`,
    );
  }
}

function checkGraph(manifest, itemBySlug) {
  invariant(Array.isArray(manifest.clusters), 'catalog clusters are required');
  invariant(Array.isArray(manifest.collections), 'catalog collections are required');
  invariant(Array.isArray(manifest.similarities), 'catalog similarities are required');
  const clusterSlugs = new Set();
  for (const cluster of manifest.clusters) {
    invariant(cluster?.slug && !clusterSlugs.has(cluster.slug), `cluster ${cluster?.slug} is duplicated or invalid`);
    clusterSlugs.add(cluster.slug);
    invariant(Array.isArray(cluster.memberSlugs) && cluster.memberSlugs.length > 0, `cluster ${cluster.slug} needs members`);
    const members = cluster.memberSlugs.map((slug) => {
      invariant(itemBySlug.has(slug), `cluster ${cluster.slug} refers to unknown item ${slug}`);
      return itemBySlug.get(slug);
    });
    invariant(cluster.memberSlugs.includes(cluster.representativeSlug), `cluster ${cluster.slug} representative is not a member`);
    invariant(new Set(members.map((item) => item.contentClass)).size === 1, `cluster ${cluster.slug} mixes content classes`);
  }
  const collectionSlugs = new Set();
  for (const collection of manifest.collections) {
    invariant(collection?.slug && !collectionSlugs.has(collection.slug), `collection ${collection?.slug} is duplicated or invalid`);
    collectionSlugs.add(collection.slug);
    invariant(Array.isArray(collection.itemSlugs) && collection.itemSlugs.length > 0, `collection ${collection.slug} needs items`);
    for (const slug of collection.itemSlugs) invariant(itemBySlug.has(slug), `collection ${collection.slug} refers to unknown item ${slug}`);
  }
  for (const edge of manifest.similarities) {
    invariant(itemBySlug.has(edge.from) && itemBySlug.has(edge.to), `similarity edge ${edge.from} -> ${edge.to} has an unknown item`);
    invariant(edge.from !== edge.to, `similarity edge ${edge.from} points to itself`);
    invariant(Number.isFinite(edge.score) && edge.score >= 0 && edge.score <= 1, `similarity edge ${edge.from} has an invalid score`);
  }
  for (const item of itemBySlug.values()) {
    for (const clusterSlug of item.clusterSlugs) invariant(clusterSlugs.has(clusterSlug), `item ${item.slug} refers to unknown cluster ${clusterSlug}`);
  }
}

async function probe(url, label) {
  const response = await fetch(url, {
    method: 'HEAD',
    redirect: 'follow',
    signal: AbortSignal.timeout(20_000),
    headers: { 'User-Agent': 'RomanPics-catalog-check/1.0' },
  });
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}`);
  if (label.endsWith('thumbnail')) {
    const mediaType = response.headers.get('content-type') ?? '';
    const contentLength = Number(response.headers.get('content-length') ?? 0);
    invariant(mediaType.startsWith('image/'), `${label} is not an image (${mediaType || 'unknown'})`);
    invariant(
      !contentLength || contentLength <= 1_000_000,
      `${label} is ${(contentLength / 1_000_000).toFixed(2)} MB; choose a web rendition`,
    );
    return `${label}: ${response.status}, ${contentLength || 'unknown'} bytes`;
  }
  return `${label}: ${response.status}`;
}

async function main() {
  const manifest = JSON.parse(await readFile(manifestUrl, 'utf8'));
  invariant(manifest.schemaVersion === 1, 'catalog schemaVersion must be 1');
  invariant(Array.isArray(manifest.items) && manifest.items.length > 0, 'catalog items are required');
  const seenIds = new Set();
  const seenSlugs = new Set();
  for (const item of manifest.items) checkItem(item, seenIds, seenSlugs);
  checkGraph(manifest, new Map(manifest.items.map((item) => [item.slug, item])));

  if (linkMode) {
    const targets = manifest.items.flatMap((item) => [
      [item.sourceUrl, `${item.slug} source`],
      [item.thumbnail, `${item.slug} thumbnail`],
    ]);
    const batchSize = 4;
    for (let index = 0; index < targets.length; index += batchSize) {
      const results = await Promise.all(
        targets.slice(index, index + batchSize).map(([url, label]) => probe(url, label)),
      );
      for (const result of results) console.log(result);
    }
  }

  console.log(`Catalog valid: ${manifest.items.length} items${linkMode ? ' with live links' : ''}.`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
