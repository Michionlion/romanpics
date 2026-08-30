'use client';

import { useMemo, useState } from 'react';
import {
  ArrowUpRight,
  Heart,
  Images,
  Layers3,
  Orbit,
  Search,
  Shuffle,
  Sparkles,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type CatalogItem = {
  id: string;
  title: string;
  contentClass:
    | 'Mission photos'
    | 'Simulations'
    | 'The telescope'
    | 'Visualizations';
  detail: string;
  image: string;
  href: string;
  credit: string;
  votes: number;
  alt: string;
  tags: string[];
};

const catalog: CatalogItem[] = [
  {
    id: 'launch-day',
    title: 'Roman begins its journey',
    contentClass: 'Mission photos',
    detail: 'Launch day · Aug 30, 2026',
    image:
      'https://images-assets.nasa.gov/image/NHQ20260830_admin_0002/NHQ20260830_admin_0002~large.jpg',
    href: 'https://images.nasa.gov/details/NHQ20260830_admin_0002',
    credit: 'NASA',
    votes: 148,
    alt: 'The Nancy Grace Roman Space Telescope launches aboard a rocket against a bright sky.',
    tags: ['launch', 'rocket', 'spacecraft', 'journey'],
  },
  {
    id: 'simulated-ultra-deep-field',
    title: 'A window into the early universe',
    contentClass: 'Simulations',
    detail: 'Roman ultra-deep field concept',
    image:
      'https://svs.gsfc.nasa.gov/vis/a010000/a013900/a013921/DREaM_Roman_15_Percent_print.jpg',
    href: 'https://svs.gsfc.nasa.gov/13921/',
    credit: 'NASA GSFC / DREaM team',
    votes: 93,
    alt: 'A simulated deep field densely filled with galaxies of many colors and shapes.',
    tags: ['galaxies', 'deep field', 'early universe', 'infrared'],
  },
  {
    id: 'fully-deployed',
    title: 'The observatory, fully deployed',
    contentClass: 'The telescope',
    detail: 'Pre-launch deployment test',
    image:
      'https://svs.gsfc.nasa.gov/vis/a010000/a014900/a014997/Drone_Footage_-_Fully_Deployed_Roman_Observatory.00001_print.jpg',
    href: 'https://svs.gsfc.nasa.gov/14997/',
    credit: 'NASA GSFC',
    votes: 71,
    alt: 'The fully deployed Roman observatory towers inside a cleanroom.',
    tags: ['hardware', 'cleanroom', 'solar panels', 'observatory'],
  },
  {
    id: 'beauty-pass',
    title: 'Roman among the stars',
    contentClass: 'Visualizations',
    detail: 'Artist’s concept · Aug 20, 2026',
    image:
      'https://svs.gsfc.nasa.gov/vis/a020000/a020400/a020416/Space_Beauty_Shot_2_16_9_1080.00951_print.jpg',
    href: 'https://svs.gsfc.nasa.gov/20416/',
    credit: 'NASA GSFC',
    votes: 64,
    alt: 'An artist’s concept of the Roman Space Telescope floating above a star field.',
    tags: ['spacecraft', 'artist concept', 'orbit', 'stars'],
  },
  {
    id: 'millions-of-galaxies',
    title: 'Millions of galaxies emerge',
    contentClass: 'Simulations',
    detail: 'Synthetic Roman deep-field view',
    image:
      'https://svs.gsfc.nasa.gov/vis/a010000/a014300/a014301/Roman_Zoom_still.jpg',
    href: 'https://svs.gsfc.nasa.gov/14301/',
    credit: 'Caltech-IPAC / R. Hurt / M. Troxel',
    votes: 58,
    alt: 'A simulated field showing layers of red, yellow, and white galaxies.',
    tags: ['galaxies', 'simulation', 'redshift', 'deep field'],
  },
  {
    id: 'wide-area-survey',
    title: 'A survey one thousand times wider',
    contentClass: 'Visualizations',
    detail: 'Roman and Hubble sky coverage',
    image:
      'https://svs.gsfc.nasa.gov/vis/a010000/a014000/a014001/Roman_HLS_FINAL_1080.png',
    href: 'https://svs.gsfc.nasa.gov/14001/',
    credit: 'NASA GSFC',
    votes: 44,
    alt: 'An illustration comparing Roman’s wide sky survey area with Hubble’s COSMOS mosaic.',
    tags: ['survey', 'hubble', 'wide field', 'dark energy'],
  },
  {
    id: 'cleanroom-at-work',
    title: 'Preparing Roman for space',
    contentClass: 'The telescope',
    detail: 'Long-exposure cleanroom photography',
    image:
      'https://svs.gsfc.nasa.gov/vis/a010000/a014900/a014993/Stationary_-_DAC_Deployment_Prepmp4.00001_print.jpg',
    href: 'https://svs.gsfc.nasa.gov/14993/',
    credit: 'NASA / Sophia Roberts',
    votes: 39,
    alt: 'Technicians prepare Roman’s deployable aperture cover inside a cleanroom.',
    tags: ['technicians', 'cleanroom', 'aperture cover', 'engineering'],
  },
  {
    id: 'journey-to-l2',
    title: 'Roman’s million-mile journey',
    contentClass: 'Visualizations',
    detail: 'Launch and orbit at Sun–Earth L2',
    image:
      'https://svs.gsfc.nasa.gov/vis/a000000/a005600/a005673/roman_orbit_close_wDates.Still003_preview.jpg',
    href: 'https://svs.gsfc.nasa.gov/5673/',
    credit: 'NASA Scientific Visualization Studio',
    votes: 35,
    alt: 'A visualization of Roman’s curved trajectory from Earth toward the Sun–Earth L2 point.',
    tags: ['orbit', 'L2', 'journey', 'spacecraft'],
  },
];

const filters = [
  'All',
  'Mission photos',
  'Simulations',
  'The telescope',
  'Visualizations',
];

const groups = [
  {
    id: 'cosmic-simulations',
    title: 'Cosmic simulations',
    description:
      'Possible Roman views of deep fields, redshift, and the early universe.',
    votes: 52,
    count: 2,
    images: [
      catalog.find((item) => item.id === 'simulated-ultra-deep-field')!.image,
      catalog.find((item) => item.id === 'millions-of-galaxies')!.image,
    ],
  },
  {
    id: 'cleanroom',
    title: 'Roman in the cleanroom',
    description:
      'The people, hardware, and careful work behind the observatory.',
    votes: 41,
    count: 2,
    images: [
      catalog.find((item) => item.id === 'fully-deployed')!.image,
      catalog.find((item) => item.id === 'cleanroom-at-work')!.image,
    ],
  },
  {
    id: 'road-to-first-light',
    title: 'The road to first light',
    description: 'Launch, the journey to L2, and what comes next for Roman.',
    votes: 38,
    count: 3,
    images: [
      catalog.find((item) => item.id === 'launch-day')!.image,
      catalog.find((item) => item.id === 'journey-to-l2')!.image,
    ],
  },
];

export default function Home() {
  const [query, setQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState('All');
  const [votes, setVotes] = useState<Set<string>>(() => new Set());
  const [groupVotes, setGroupVotes] = useState<Set<string>>(() => new Set());

  const visibleItems = useMemo(() => {
    const needle = query.trim().toLowerCase();

    return catalog.filter((item) => {
      const matchesFilter =
        activeFilter === 'All' || item.contentClass === activeFilter;
      const haystack = [
        item.title,
        item.detail,
        item.contentClass,
        item.credit,
        ...item.tags,
      ]
        .join(' ')
        .toLowerCase();
      return matchesFilter && (!needle || haystack.includes(needle));
    });
  }, [activeFilter, query]);

  function toggleVote(id: string) {
    setVotes((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function surpriseMe() {
    const pool = visibleItems.length ? visibleItems : catalog;
    const pick = pool[Math.floor(Math.random() * pool.length)];
    window.open(pick.href, '_blank', 'noopener,noreferrer');
  }

  function toggleGroupVote(id: string) {
    setGroupVotes((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <main className="min-h-screen overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none fixed inset-x-0 top-0 h-[32rem] bg-[radial-gradient(circle_at_18%_0%,oklch(0.72_0.16_260/0.16),transparent_42%),radial-gradient(circle_at_78%_12%,oklch(0.82_0.15_78/0.12),transparent_36%)]" />

      <header className="relative border-b border-white/8">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
          <a
            className="flex items-center gap-2.5"
            href="#top"
            aria-label="Roman Pics home"
          >
            <span className="grid size-9 place-items-center rounded-full border border-amber-200/30 bg-amber-200/10 text-amber-200">
              <Orbit className="size-[1.15rem]" aria-hidden="true" />
            </span>
            <span className="font-heading text-lg font-semibold tracking-tight">
              Roman<span className="text-amber-200">Pics</span>
            </span>
          </a>

          <nav
            className="flex items-center gap-1"
            aria-label="Primary navigation"
          >
            <Button
              variant="ghost"
              className="hidden text-slate-300 hover:bg-white/8 sm:inline-flex"
              onClick={() =>
                document
                  .querySelector('#about-the-archive')
                  ?.scrollIntoView({ behavior: 'smooth' })
              }
            >
              About the archive
            </Button>
            <a
              className={buttonVariants({
                variant: 'outline',
                className:
                  'border-white/12 bg-white/5 text-slate-100 hover:bg-white/10',
              })}
              href="https://github.com/Michionlion/romanpics"
              target="_blank"
              rel="noreferrer"
            >
              GitHub
              <ArrowUpRight data-icon="inline-end" />
            </a>
          </nav>
        </div>
      </header>

      <section
        id="top"
        className="relative mx-auto max-w-7xl px-5 pb-10 pt-12 sm:px-8 sm:pt-16"
      >
        <div className="max-w-3xl">
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <Badge className="border border-emerald-300/20 bg-emerald-300/10 text-emerald-200">
              <span
                className="size-1.5 rounded-full bg-emerald-300"
                aria-hidden="true"
              />
              Roman launched Aug 30, 2026
            </Badge>
            <span className="text-xs text-slate-400">
              Science images will follow commissioning
            </span>
          </div>
          <h1 className="font-heading text-4xl leading-[1.03] font-semibold tracking-[-0.04em] text-balance sm:text-6xl">
            The wide universe,
            <span className="block text-amber-200">easy to explore.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
            Find beautiful images connected to NASA’s Roman Space Telescope—from
            today’s mission photos and simulations to tomorrow’s public science
            observations.
          </p>
        </div>

        <search className="mt-8 block max-w-3xl">
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              document
                .querySelector('#catalog')
                ?.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            <div className="relative min-w-0 flex-1">
              <Search
                className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                aria-hidden="true"
              />
              <Input
                className="h-12 rounded-xl border-white/12 bg-white/[0.07] pl-11 text-base text-white shadow-xl shadow-black/10 placeholder:text-slate-500 focus-visible:border-amber-200/50 focus-visible:ring-amber-200/15"
                placeholder="Try “galaxies,” “coronagraph,” or “launch”…"
                aria-label="Search the Roman image catalog"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <Button className="h-12 rounded-xl bg-amber-200 px-5 text-slate-950 hover:bg-amber-100">
              Explore
            </Button>
          </form>
        </search>

        <div
          className="mt-4 flex gap-2 overflow-x-auto pb-2"
          aria-label="Catalog filters"
        >
          {filters.map((filter) => (
            <Button
              key={filter}
              type="button"
              size="sm"
              variant={activeFilter === filter ? 'secondary' : 'outline'}
              aria-pressed={activeFilter === filter}
              onClick={() => setActiveFilter(filter)}
              className={
                activeFilter === filter
                  ? 'rounded-full bg-white text-slate-950 hover:bg-slate-100'
                  : 'rounded-full border-white/10 bg-transparent text-slate-300 hover:bg-white/8'
              }
            >
              {filter}
            </Button>
          ))}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="rounded-full text-amber-200 hover:bg-amber-200/10 hover:text-amber-100"
            onClick={surpriseMe}
          >
            <Shuffle data-icon="inline-start" />
            Surprise me
          </Button>
        </div>
      </section>

      <section
        id="catalog"
        className="relative mx-auto max-w-7xl scroll-mt-6 px-5 pb-20 sm:px-8"
      >
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="mb-1 flex items-center gap-2 text-xs font-medium tracking-[0.16em] text-amber-200 uppercase">
              <Sparkles className="size-3.5" aria-hidden="true" />
              Community favorites
            </p>
            <h2 className="font-heading text-2xl font-semibold tracking-tight">
              Start exploring
            </h2>
          </div>
          <span className="hidden items-center gap-2 text-sm text-slate-400 sm:flex">
            <Images className="size-4" aria-hidden="true" />
            {visibleItems.length}{' '}
            {visibleItems.length === 1 ? 'result' : 'results'}
          </span>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {visibleItems.map((item, index) => (
            <article
              key={item.title}
              className={`group relative min-h-[23rem] overflow-hidden rounded-2xl border border-white/10 bg-slate-900 ${
                index === 0 ? 'md:col-span-2' : ''
              }`}
            >
              <img
                src={item.image}
                alt={item.alt}
                className="absolute inset-0 h-full w-full object-cover transition duration-700 group-hover:scale-[1.025]"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/25 to-transparent" />
              <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-4 p-5 sm:p-6">
                <div>
                  <Badge className="mb-3 border border-white/15 bg-slate-950/55 text-slate-100 backdrop-blur-sm">
                    {item.contentClass === 'Simulations'
                      ? 'Simulated · not observed'
                      : item.contentClass}
                  </Badge>
                  <h3 className="max-w-lg font-heading text-xl font-semibold tracking-tight text-white sm:text-2xl">
                    <a
                      href={item.href}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-sm hover:text-amber-100 focus-visible:outline-2 focus-visible:outline-amber-200"
                    >
                      {item.title}
                    </a>
                  </h3>
                  <p className="mt-1 text-sm text-slate-300">
                    {item.detail} · {item.credit}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => toggleVote(item.id)}
                  aria-label={`${votes.has(item.id) ? 'Remove vote from' : 'Upvote'} ${item.title}`}
                  aria-pressed={votes.has(item.id)}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-2 text-sm font-medium text-white backdrop-blur-sm transition focus-visible:outline-2 focus-visible:outline-amber-200 ${
                    votes.has(item.id)
                      ? 'border-rose-300/40 bg-rose-400/25'
                      : 'border-white/15 bg-slate-950/55 hover:bg-slate-900/80'
                  }`}
                >
                  <Heart
                    className={`size-4 ${votes.has(item.id) ? 'fill-current' : ''}`}
                    aria-hidden="true"
                  />
                  {item.votes + (votes.has(item.id) ? 1 : 0)}
                </button>
              </div>
            </article>
          ))}
        </div>

        {visibleItems.length === 0 && (
          <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.035] px-6 py-14 text-center">
            <p className="font-heading text-xl font-semibold">
              No matches in this preview
            </p>
            <p className="mt-2 text-sm text-slate-400">
              Try a broader search or look in every category.
            </p>
            <Button
              className="mt-5 bg-amber-200 text-slate-950 hover:bg-amber-100"
              onClick={() => {
                setQuery('');
                setActiveFilter('All');
              }}
            >
              Clear filters
            </Button>
          </div>
        )}

        <aside
          id="about-the-archive"
          className="mt-5 flex scroll-mt-6 flex-col justify-between gap-4 rounded-2xl border border-dashed border-white/15 bg-white/[0.035] p-5 sm:flex-row sm:items-center"
        >
          <div>
            <p className="font-medium text-slate-100">What’s here today?</p>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
              This preview mixes official mission photography, visualizations,
              and clearly labeled simulations. Once processed Roman observations
              arrive in MAST, the catalog will link directly to those public
              originals.
            </p>
          </div>
          <a
            className={buttonVariants({
              variant: 'outline',
              className:
                'shrink-0 border-white/12 bg-white/5 text-slate-100 hover:bg-white/10',
            })}
            href="https://archive.stsci.edu/missions-and-data/roman"
            target="_blank"
            rel="noreferrer"
          >
            Visit MAST
            <ArrowUpRight data-icon="inline-end" />
          </a>
        </aside>

        <section className="mt-16" aria-labelledby="groups-title">
          <div className="mb-5 max-w-2xl">
            <p className="mb-1 flex items-center gap-2 text-xs font-medium tracking-[0.16em] text-amber-200 uppercase">
              <Layers3 className="size-3.5" aria-hidden="true" />
              Visual neighborhoods
            </p>
            <h2
              id="groups-title"
              className="font-heading text-2xl font-semibold tracking-tight"
            >
              More to love, together
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Related pictures will live in evolving groups. Vote for a whole
              group, then choose the standout image inside it.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {groups.map((group) => (
              <article
                key={group.id}
                className="rounded-2xl border border-white/10 bg-white/[0.04] p-3"
              >
                <div className="grid h-40 grid-cols-2 gap-1.5 overflow-hidden rounded-xl bg-slate-900">
                  {group.images.map((image, index) => (
                    <img
                      key={image}
                      src={image}
                      alt=""
                      className={`h-full w-full object-cover ${index === 0 ? 'rounded-l-xl' : 'rounded-r-xl'}`}
                    />
                  ))}
                </div>
                <div className="flex items-start justify-between gap-3 p-2 pb-1 pt-4">
                  <div>
                    <h3 className="font-heading text-lg font-semibold tracking-tight text-slate-100">
                      {group.title}
                    </h3>
                    <p className="mt-1 text-sm leading-5 text-slate-400">
                      {group.description}
                    </p>
                    <p className="mt-3 text-xs font-medium text-slate-500">
                      {group.count} pictures in this preview
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => toggleGroupVote(group.id)}
                    aria-label={`${groupVotes.has(group.id) ? 'Remove vote from' : 'Upvote'} group ${group.title}`}
                    aria-pressed={groupVotes.has(group.id)}
                    className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-2 text-sm font-medium text-white transition focus-visible:outline-2 focus-visible:outline-amber-200 ${
                      groupVotes.has(group.id)
                        ? 'border-rose-300/40 bg-rose-400/25'
                        : 'border-white/10 bg-white/[0.055] hover:bg-white/10'
                    }`}
                  >
                    <Heart
                      className={`size-4 ${groupVotes.has(group.id) ? 'fill-current' : ''}`}
                      aria-hidden="true"
                    />
                    {group.votes + (groupVotes.has(group.id) ? 1 : 0)}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      </section>

      <footer className="relative border-t border-white/8">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-5 px-5 py-8 text-sm text-slate-400 sm:flex-row sm:items-center sm:px-8">
          <div>
            <p className="font-medium text-slate-200">
              RomanPics is an independent open-source project.
            </p>
            <p className="mt-1">
              Not affiliated with or endorsed by NASA, STScI, or IPAC.
            </p>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            <a
              className="hover:text-amber-200"
              href="https://science.nasa.gov/mission/roman-space-telescope/"
              target="_blank"
              rel="noreferrer"
            >
              NASA Roman
            </a>
            <a
              className="hover:text-amber-200"
              href="https://archive.stsci.edu/missions-and-data/roman"
              target="_blank"
              rel="noreferrer"
            >
              Roman at MAST
            </a>
            <a
              className="hover:text-amber-200"
              href="https://github.com/Michionlion/romanpics"
              target="_blank"
              rel="noreferrer"
            >
              Project source
            </a>
          </div>
        </div>
      </footer>
    </main>
  );
}
