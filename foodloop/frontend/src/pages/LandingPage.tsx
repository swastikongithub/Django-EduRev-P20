import {
  ArrowRight,
  BadgeCheck,
  ChefHat,
  CircleCheck,
  ExternalLink,
  Flame,
  Hourglass,
  IndianRupee,
  Scale,
  Search,
  ShieldCheck,
  Thermometer,
  Ticket,
  Timer,
  UtensilsCrossed,
  Wheat,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useAllListings, useKitchens } from "../api/queries";
import type { Listing, MealType } from "../api/types";
import { FaqList } from "../components/Faq";
import { KitchenCard } from "../components/KitchenCard";
import { ListingCard, ListingCardSkeleton } from "../components/ListingCard";
import { Countdown, CountUp, DealTicker, LiveDot, Rail, Reveal } from "../components/Live";
import { MenuRow } from "../components/MenuRow";
import { Photo } from "../components/Photo";
import { ErrorState, Notice, Skeleton } from "../components/ui";
import { FAQ } from "../lib/faq";
import { formatRupees, minutesUntil } from "../lib/format";
import { CATEGORY_PHOTOS, PHOTOS, photoForMeal } from "../lib/photos";

const byClosingTime = (a: Listing, b: Listing) => a.reservations_close_at.localeCompare(b.reservations_close_at);

// ---------------------------------------------------------------------------------------------------------
// Hero: dark green, live numbers from the API, a real "closing soon" deal and a ticker of live deals
// ---------------------------------------------------------------------------------------------------------

function ClosingSoonCard({ listing }: { listing: Listing }) {
  return (
    <Link
      to={`/meals/${listing.id}`}
      className="absolute -bottom-8 left-3 w-[250px] animate-float rounded-2xl bg-white p-3 text-ink-900 shadow-lift ring-1 ring-black/5 transition hover:ring-leaf-300 sm:-left-8 sm:bottom-12 sm:w-[285px]"
    >
      <p className="flex items-center gap-1.5 text-[10.5px] font-bold tracking-wider text-saffron-600 uppercase">
        <Flame className="size-3.5" aria-hidden="true" /> Closing soon
      </p>
      <div className="mt-2 flex gap-3">
        <div className="size-14 shrink-0 overflow-hidden rounded-xl">
          <Photo photo={photoForMeal(listing.meal_type, listing.title, listing.id)} sizes="56px" alt="" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-[14px] font-semibold">{listing.title}</p>
          <p className="text-[14px]">
            <span className="font-bold text-leaf-700">{formatRupees(listing.price_paise)}</span>{" "}
            <span className="text-ink-500 line-through">{formatRupees(listing.original_price_paise)}</span>
          </p>
        </div>
      </div>
      <div className="mt-2.5 flex items-center justify-between rounded-xl bg-sage-50 px-3 py-2 text-[12px]">
        <Countdown to={listing.reservations_close_at} />
        <span className="font-semibold text-leaf-700">{listing.quantity_available} left</span>
      </div>
    </Link>
  );
}

function HeroMosaic({ closing }: { closing?: Listing }) {
  return (
    <div className="relative mx-auto w-full max-w-[560px] lg:max-w-none">
      <div className="grid h-[320px] grid-cols-[1.35fr_1fr] grid-rows-2 gap-3 sm:h-[440px] sm:gap-4 lg:h-[520px]">
        <div className="row-span-2 overflow-hidden rounded-[2rem] shadow-lift ring-1 ring-white/10">
          <Photo photo={PHOTOS.thaliSpread} priority sizes="(min-width: 1024px) 30vw, 58vw" />
        </div>
        <div className="overflow-hidden rounded-[1.6rem] shadow-lift ring-1 ring-white/10">
          <Photo photo={PHOTOS.masalaDosa} sizes="(min-width: 1024px) 20vw, 38vw" />
        </div>
        <div className="overflow-hidden rounded-[1.6rem] shadow-lift ring-1 ring-white/10">
          <Photo photo={PHOTOS.biryaniBowl} sizes="(min-width: 1024px) 20vw, 38vw" />
        </div>
      </div>
      {closing && <ClosingSoonCard listing={closing} />}
    </div>
  );
}

function Hero({ live }: { live: Listing[] }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const kitchens = new Set(live.map((listing) => listing.provider.id)).size;
  const bestDeal = live.reduce((best, listing) => Math.max(best, listing.discount_percent), 0);
  // The soonest deal that still has a few minutes left, so the card doesn't vanish the moment you see it.
  const closing = [...live].sort(byClosingTime).find((listing) => minutesUntil(listing.reservations_close_at) >= 5);
  const deals = [...live].sort((a, b) => b.discount_percent - a.discount_percent || byClosingTime(a, b));

  function search(event: FormEvent) {
    event.preventDefault();
    navigate(query.trim() ? `/meals?q=${encodeURIComponent(query.trim())}` : "/meals");
  }

  return (
    <section className="relative -mt-[4.25rem] overflow-hidden bg-leaf-900 pt-[4.25rem] text-white">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -top-48 -right-40 size-[40rem] animate-glow rounded-full bg-saffron-500/25 blur-3xl" />
        <div className="absolute top-1/3 -left-48 size-[34rem] animate-glow rounded-full bg-leaf-500/35 blur-3xl [animation-delay:-4s]" />
        <div className="absolute inset-0 bg-[radial-gradient(rgb(255_255_255/0.07)_1px,transparent_1.3px)] [background-size:22px_22px]" />
      </div>

      <div className="container-page relative grid grid-cols-1 items-center gap-14 pt-8 pb-16 sm:pt-12 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:pt-14 lg:pb-20">
        <div className="relative z-10 animate-rise">
          <p className="glass inline-flex items-center gap-2.5 rounded-full py-1.5 pr-4 pl-3 text-[13px] font-semibold">
            <LiveDot />
            {live.length > 0 ? `${live.length} meals you can reserve right now` : "Surplus meals from campus & city kitchens"}
          </p>
          <h1 className="mt-6 text-[2.7rem] leading-[1.02] text-white sm:text-6xl lg:text-[4.3rem]">
            Good food deserves <span className="text-sunrise">another chance.</span>
          </h1>
          <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-white/80 sm:text-xl">
            Discover delicious surplus meals at lower prices while helping reduce food waste.
          </p>

          <form role="search" onSubmit={search} className="mt-8 flex max-w-xl items-center gap-2 rounded-full bg-white p-1.5 pl-5 shadow-lift">
            <Search className="size-5 shrink-0 text-ink-500" aria-hidden="true" />
            <label htmlFor="hero-search" className="sr-only">
              Search meals, kitchens or areas
            </label>
            <input
              id="hero-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Try dosa, biryani or chai…"
              className="min-w-0 flex-1 bg-transparent py-2 text-[15.5px] text-ink-900 outline-none placeholder:text-ink-500"
            />
            <button type="submit" className="btn-primary px-6">
              Search
            </button>
          </form>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <Link to="/meals" className="btn-accent btn-lg">
              Explore Meals <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
            <Link to="/register/kitchen" className="btn btn-lg glass text-white hover:bg-white/20">
              <ChefHat className="size-4" aria-hidden="true" /> Become a Partner
            </Link>
          </div>

          {live.length > 0 && (
            <dl className="mt-10 grid max-w-xl grid-cols-3 gap-3">
              {[
                { label: "Meals live now", value: live.length, format: String },
                { label: "Kitchens", value: kitchens, format: String },
                { label: "Best deal", value: bestDeal, format: (n: number) => `${n}% off` },
              ].map((stat) => (
                <div key={stat.label} className="glass flex flex-col-reverse rounded-2xl px-4 py-3">
                  <dt className="text-[12.5px] text-white/65">{stat.label}</dt>
                  <dd className="font-display text-xl font-bold whitespace-nowrap sm:text-2xl lg:text-[1.75rem]">
                    <CountUp value={stat.value} format={stat.format} />
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        <HeroMosaic closing={closing} />
      </div>

      {deals.length > 0 && (
        <div className="relative border-t border-white/10 bg-black/10 py-3.5">
          <div className="container-page flex items-center gap-5">
            <span className="hidden shrink-0 items-center gap-2 text-[12px] font-bold tracking-[0.14em] text-turmeric-300 uppercase sm:flex">
              <LiveDot /> Live deals
            </span>
            <div className="min-w-0 flex-1">
              <DealTicker listings={deals} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------
// Live sections: categories, closing soon, today's menu, kitchens (all real API data)
// ---------------------------------------------------------------------------------------------------------

function Categories({ live }: { live: Listing[] }) {
  const counts = live.reduce<Partial<Record<MealType, number>>>((all, listing) => {
    all[listing.meal_type] = (all[listing.meal_type] ?? 0) + 1;
    return all;
  }, {});
  return (
    <section aria-labelledby="cravings-title" className="container-page pt-16 sm:pt-20">
      <Reveal className="flex items-end justify-between gap-4">
        <div>
          <p className="eyebrow">What are you craving?</p>
          <h2 id="cravings-title" className="mt-2 text-3xl sm:text-4xl">
            Browse by meal
          </h2>
        </div>
        <Link to="/menu" className="text-sm font-semibold text-leaf-700 underline-offset-4 hover:underline">
          Full menu
        </Link>
      </Reveal>
      <ul className="mt-8 grid grid-cols-3 gap-x-3 gap-y-7 sm:grid-cols-6 sm:gap-5">
        {CATEGORY_PHOTOS.map((category, index) => (
          <Reveal as="li" key={category.mealType} delay={index * 70}>
            <Link to={`/meals?meal=${category.mealType}`} className="group flex flex-col items-center gap-3 rounded-2xl text-center">
              <span className="relative block aspect-square w-full max-w-[150px] overflow-hidden rounded-full shadow-soft ring-4 ring-white transition duration-300 group-hover:-translate-y-1 group-hover:shadow-lift group-hover:ring-leaf-100">
                <Photo photo={category.photo} sizes="(min-width: 640px) 150px, 30vw" className="transition duration-700 group-hover:scale-110" />
              </span>
              <span>
                <span className="block text-[14px] font-semibold text-ink-900 group-hover:text-leaf-700 sm:text-[15px]">
                  {category.label}
                </span>
                <span className="text-[12.5px] text-ink-500">
                  {counts[category.mealType] ? `${counts[category.mealType]} available` : "None right now"}
                </span>
              </span>
            </Link>
          </Reveal>
        ))}
      </ul>
    </section>
  );
}

function EmptyMeals() {
  return (
    <div className="card grid grid-cols-1 items-center gap-8 overflow-hidden p-6 sm:p-10 md:grid-cols-[1fr_1.2fr]">
      <div className="relative mx-auto h-40 w-64" aria-hidden="true">
        {[PHOTOS.masalaChai, PHOTOS.idliVada, PHOTOS.biryaniPan].map((item, index) => (
          <div
            key={item.slug}
            className="absolute top-1/2 size-28 -translate-y-1/2 overflow-hidden rounded-full shadow-soft ring-4 ring-white"
            style={{ left: `${index * 68}px`, zIndex: index === 1 ? 2 : 1 }}
          >
            <Photo photo={item} sizes="112px" alt="" />
          </div>
        ))}
      </div>
      <div>
        <h3 className="text-xl">No meals listed right now</h3>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-600">
          Kitchens usually post their surplus right after lunch and dinner service. Create a free account now so
          you're ready to reserve the moment something good comes up.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link to="/register" className="btn-primary">
            Create free account
          </Link>
          <Link to="/kitchens" className="btn-secondary">
            See the kitchens
          </Link>
        </div>
      </div>
    </div>
  );
}

function ClosingSoon({ live, isLoading, error, retry }: { live: Listing[]; isLoading: boolean; error: unknown; retry: () => void }) {
  const soonest = [...live].sort(byClosingTime).slice(0, 10);
  const hasSample = soonest.some((listing) => listing.provider.is_sample);
  return (
    <section aria-labelledby="closing-title" className="container-page pt-20 sm:pt-24">
      <Reveal className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow flex items-center gap-2">
            <LiveDot /> Closing soon
          </p>
          <h2 id="closing-title" className="mt-2 text-3xl sm:text-4xl">
            Grab it before it's gone
          </h2>
          <p className="mt-2 max-w-xl text-[15px] text-ink-600">
            Live from approved kitchens, soonest first. Portions and timers update on their own.
          </p>
        </div>
        <Link to="/meals" className="btn-secondary">
          Explore all meals <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </Reveal>
      {hasSample && (
        <Notice tone="info" className="mt-6">
          These are <strong>sample listings</strong> for demonstration. The kitchens, meals and prices aren't real.
        </Notice>
      )}
      <div className="mt-8">
        {isLoading ? (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((key) => (
              <ListingCardSkeleton key={key} />
            ))}
          </div>
        ) : error ? (
          <div className="card">
            <ErrorState error={error} onRetry={retry} />
          </div>
        ) : soonest.length === 0 ? (
          <EmptyMeals />
        ) : (
          <Rail label="Meals closing soon">
            {soonest.map((listing, index) => (
              <div key={listing.id} className="flex w-[285px] shrink-0 snap-start sm:w-[320px] [&>a]:w-full">
                <ListingCard listing={listing} index={index} />
              </div>
            ))}
          </Rail>
        )}
      </div>
    </section>
  );
}

function MenuPreview({ live }: { live: Listing[] }) {
  if (live.length === 0) return null;
  // A little of everything: take dishes from each meal type in turn, cheapest first.
  const byType = new Map<MealType, Listing[]>();
  for (const listing of [...live].sort((a, b) => a.price_paise - b.price_paise)) {
    byType.set(listing.meal_type, [...(byType.get(listing.meal_type) ?? []), listing]);
  }
  const picks: Listing[] = [];
  for (let round = 0; picks.length < 8 && round < 8; round++) {
    for (const list of byType.values()) if (list[round] && picks.length < 8) picks.push(list[round]);
  }
  const cheapest = Math.min(...live.map((listing) => listing.price_paise));
  return (
    <section aria-labelledby="menu-title" className="container-page pt-20 sm:pt-24">
      <Reveal className="overflow-hidden rounded-[2rem] border border-line/80 bg-white/80 shadow-soft backdrop-blur">
        <div className="grid grid-cols-1 lg:grid-cols-[0.8fr_1.6fr]">
          <div className="relative flex flex-col justify-between gap-8 bg-sage-100/70 p-8 sm:p-10">
            <div>
              <p className="eyebrow">Today's menu</p>
              <h2 id="menu-title" className="mt-2 text-3xl sm:text-4xl">
                Every dish, every price.
              </h2>
              <p className="mt-3 text-[15px] leading-relaxed text-ink-600">
                {live.length} dishes from approved kitchens right now, starting at {formatRupees(cheapest)}. Prices are
                set by each kitchen and you pay at the counter.
              </p>
            </div>
            <div className="hidden gap-3 lg:flex" aria-hidden="true">
              {[PHOTOS.vadaPav, PHOTOS.poha, PHOTOS.lassi].map((photo) => (
                <div key={photo.slug} className="size-20 overflow-hidden rounded-2xl shadow-soft ring-4 ring-white">
                  <Photo photo={photo} sizes="80px" alt="" />
                </div>
              ))}
            </div>
            <Link to="/menu" className="btn-primary self-start">
              See the full menu <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </div>
          <div className="grid grid-cols-1 gap-x-6 gap-y-1 p-4 sm:p-6 md:grid-cols-2">
            {picks.map((listing) => (
              <MenuRow key={listing.id} listing={listing} />
            ))}
          </div>
        </div>
      </Reveal>
    </section>
  );
}

function Kitchens({ live }: { live: Listing[] }) {
  const { data: kitchens, isLoading } = useKitchens();
  if (!isLoading && !kitchens?.length) return null;
  return (
    <section aria-labelledby="kitchens-title" className="container-page pt-20 sm:pt-24">
      <Reveal className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Kitchens on FoodLoop</p>
          <h2 id="kitchens-title" className="mt-2 text-3xl sm:text-4xl">
            Cooked by kitchens you can trust
          </h2>
          <p className="mt-2 max-w-xl text-[15px] text-ink-600">Every kitchen here is FSSAI-registered and approved by FoodLoop.</p>
        </div>
        <Link to="/kitchens" className="btn-secondary">
          All kitchens <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </Reveal>
      <div className="mt-8">
        {isLoading ? (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-80 rounded-[1.25rem]" />
            ))}
          </div>
        ) : (
          <Rail label="Kitchens">
            {kitchens!.map((kitchen) => (
              <div key={kitchen.id} className="flex w-[285px] shrink-0 snap-start sm:w-[340px] [&>a]:w-full">
                <KitchenCard kitchen={kitchen} dishes={live.filter((listing) => listing.provider.slug === kitchen.slug)} />
              </div>
            ))}
          </Rail>
        )}
      </div>
    </section>
  );
}

function FaqPreview() {
  return (
    <section aria-labelledby="faq-title" className="container-page pt-20 sm:pt-24">
      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[0.8fr_1.2fr]">
        <Reveal>
          <p className="eyebrow">Questions</p>
          <h2 id="faq-title" className="mt-2 text-3xl sm:text-4xl">
            Good to know
          </h2>
          <p className="mt-3 max-w-md text-[15px] leading-relaxed text-ink-600">
            How paying, pickups and safety work. Can't find your answer? We're happy to help.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/faq" className="btn-secondary">
              All questions
            </Link>
            <Link to="/contact" className="btn-ghost">
              Contact us
            </Link>
          </div>
        </Reveal>
        <Reveal delay={100}>
          <FaqList items={FAQ[0].items.slice(0, 4)} />
        </Reveal>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------
// How it works
// ---------------------------------------------------------------------------------------------------------

function ReserveMock() {
  return (
    <div className="flex h-full items-center justify-center bg-sage-100 p-5" aria-hidden="true">
      <div className="w-full max-w-[230px] rounded-[1.4rem] bg-white p-3 shadow-lift ring-1 ring-black/5">
        <div className="flex items-center gap-2.5">
          <div className="size-11 overflow-hidden rounded-lg">
            <Photo photo={PHOTOS.steelThali} sizes="44px" alt="" />
          </div>
          <div className="min-w-0 text-left">
            <p className="truncate text-[13px] font-semibold text-ink-900">Veg thali × 2</p>
            <p className="text-[12px] text-ink-500">Pay ₹80 at pickup</p>
          </div>
        </div>
        <div className="mt-3 rounded-xl bg-leaf-600 px-3 py-2 text-center text-[12.5px] font-semibold text-white">
          <span className="inline-flex items-center gap-1.5">
            <CircleCheck className="size-4" /> Reserved
          </span>
        </div>
        <div className="mt-2 rounded-xl border-2 border-dashed border-leaf-200 bg-leaf-50 py-2 text-center font-mono text-base font-bold tracking-[0.25em] text-leaf-800">
          K7Q2MX
        </div>
      </div>
    </div>
  );
}

const STEPS = [
  {
    title: "Discover available meals",
    body: "Browse surplus from approved kitchens near you, with clear prices, allergens and pickup times.",
    media: <Photo photo={PHOTOS.lunchTray} sizes="(min-width: 768px) 30vw, 92vw" />,
  },
  {
    title: "Reserve your meal",
    body: "Choose how many portions you want and reserve in seconds. You get a pickup code instantly, and you pay the kitchen at the counter.",
    media: <ReserveMock />,
  },
  {
    title: "Collect it before the deadline",
    body: "Show your code within the pickup window and enjoy your meal while it's fresh. Plans changed? Cancel so someone else can have it.",
    media: <Photo photo={PHOTOS.takeawayBag} sizes="(min-width: 768px) 30vw, 92vw" />,
  },
];

function HowItWorks() {
  return (
    <section id="how-it-works" className="mt-24 scroll-mt-24 border-y border-line/70 bg-white/85 backdrop-blur">
      <div className="container-page py-20 lg:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">How it works</p>
          <h2 className="mt-3 text-3xl sm:text-[2.6rem] sm:leading-tight">From surplus to your plate in three steps</h2>
          <p className="mt-4 text-[16px] text-ink-600">
            No delivery fees, no waiting around. Just good food collected straight from the kitchen.
          </p>
        </div>
        <ol className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li
              key={step.title}
              className="group flex flex-col rounded-[1.75rem] border border-line/80 bg-cream-50 p-3 transition duration-300 hover:-translate-y-1 hover:shadow-lift"
            >
              <div className="relative aspect-[4/3] overflow-hidden rounded-[1.3rem] bg-sage-100 [&_img]:transition [&_img]:duration-700 group-hover:[&_img]:scale-105">
                {step.media}
                <span className="font-display absolute top-3 left-3 grid size-10 place-items-center rounded-full bg-white text-lg font-bold text-leaf-700 shadow-soft">
                  {index + 1}
                </span>
              </div>
              <div className="px-3 pt-5 pb-4">
                <h3 className="text-xl">{step.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-600">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------
// Safety, sustainability, providers
// ---------------------------------------------------------------------------------------------------------

const SAFETY = [
  {
    icon: BadgeCheck,
    title: "Approved kitchens only",
    body: "We check every kitchen's FSSAI registration before it can list anything. If a registration expires, sales stop automatically.",
  },
  {
    icon: Hourglass,
    title: "Expired food can't be sold",
    body: "Every meal has a pickup deadline and an eat-by time. The system checks the clock at the moment you reserve.",
  },
  {
    icon: Wheat,
    title: "Allergens on every batch",
    body: "Kitchens declare allergens, veg/non-veg status and any shared-kitchen risk for every listing.",
  },
  {
    icon: Thermometer,
    title: "Stored the right way",
    body: "Kitchens confirm whether food was kept hot, chilled or shelf-stable. Room-temperature food gets a much shorter window.",
  },
];

function Safety() {
  return (
    <section id="safety" className="container-page scroll-mt-24 py-20 lg:py-24">
      <div className="grid grid-cols-1 gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
        <div>
          <p className="eyebrow">Safety, built in</p>
          <h2 className="mt-3 text-3xl sm:text-[2.6rem] sm:leading-tight">Cheaper never means riskier.</h2>
          <p className="mt-4 text-[16px] leading-relaxed text-ink-600">
            Surplus food is only worth saving if it's safe to eat. These rules aren't left to good intentions: the
            platform enforces them every time.
          </p>
          <div className="mt-8 flex items-center gap-4 rounded-2xl border border-line bg-white p-4 shadow-soft">
            <ShieldCheck className="size-9 shrink-0 text-leaf-600" aria-hidden="true" />
            <p className="text-[14px] leading-snug text-ink-700">
              Pickup only, no delivery. Food goes straight from the kitchen counter to you, inside its safe window.
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {SAFETY.map((item) => (
            <div key={item.title} className="card p-6 transition duration-300 hover:-translate-y-0.5 hover:shadow-lift">
              <div className="grid size-11 place-items-center rounded-2xl bg-leaf-50 text-leaf-700">
                <item.icon className="size-5.5" aria-hidden="true" />
              </div>
              <h3 className="mt-4 text-lg">{item.title}</h3>
              <p className="mt-1.5 text-[14.5px] leading-relaxed text-ink-600">{item.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Sustainability() {
  return (
    <section id="impact" className="scroll-mt-24 bg-sage-100/70">
      <div className="container-page grid grid-cols-1 gap-12 py-20 lg:grid-cols-[0.95fr_1.05fr] lg:items-center lg:gap-16 lg:py-24">
        <figure className="relative mx-auto w-full max-w-md lg:max-w-none">
          <div className="aspect-[4/5] overflow-hidden rounded-[2rem] shadow-lift sm:aspect-[5/6]">
            <Photo photo={PHOTOS.foodWaste} sizes="(min-width: 1024px) 40vw, 90vw" />
          </div>
          <figcaption className="absolute right-4 bottom-4 left-4 rounded-2xl bg-white/92 px-4 py-3 text-[14px] font-medium text-ink-700 shadow-soft backdrop-blur sm:right-auto sm:max-w-xs">
            Food cooked to be eaten shouldn't end its day in the bin.
          </figcaption>
        </figure>
        <div>
          <p className="eyebrow">Why it matters</p>
          <h2 className="mt-3 text-3xl sm:text-[2.6rem] sm:leading-tight">Every day, good food goes uneaten.</h2>
          <p className="mt-4 text-[16px] leading-relaxed text-ink-700">
            Canteens and messes cook ahead for demand they can't predict exactly. At the end of service, some food
            is often still safe and delicious, but there's no simple way to offer it to people nearby before it
            has to be thrown away. FoodLoop is that simple way.
          </p>
          <dl className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-2xl bg-white p-5 shadow-soft">
              <dt className="text-[14px] leading-snug text-ink-600">Food wasted worldwide in 2022</dt>
              <dd className="font-display mt-1.5 text-[1.9rem] leading-tight font-bold text-leaf-700">1.05 billion tonnes</dd>
            </div>
            <div className="rounded-2xl bg-white p-5 shadow-soft">
              <dt className="text-[14px] leading-snug text-ink-600">Share of food available to consumers that was wasted</dt>
              <dd className="font-display mt-1.5 text-[1.9rem] leading-tight font-bold text-leaf-700">19%</dd>
            </div>
          </dl>
          <p className="mt-3 text-[13px] text-ink-500">
            Source:{" "}
            <a
              className="inline-flex items-center gap-1 font-medium text-leaf-700 underline-offset-4 hover:underline"
              href="https://www.unep.org/resources/publication/food-waste-index-report-2024"
              target="_blank"
              rel="noreferrer noopener"
            >
              UNEP Food Waste Index Report 2024 <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          </p>
          <div className="mt-8 flex gap-3 rounded-2xl border border-sage-300 bg-sage-50 p-4">
            <Scale className="mt-0.5 size-5 shrink-0 text-leaf-700" aria-hidden="true" />
            <p className="text-[14px] leading-relaxed text-ink-700">
              <strong className="text-ink-900">Our own impact numbers come later, and honestly.</strong> FoodLoop
              will publish figures only from measured pilot data, such as portions collected and leftovers weighed.
              We won't publish estimates.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

const PROVIDER_BENEFITS = [
  { icon: IndianRupee, title: "Recover costs", body: "Sell safe leftovers at a price you choose instead of writing them off." },
  { icon: Timer, title: "List in under a minute", body: "Add portions, price and pickup time right after service." },
  { icon: Ticket, title: "Simple handover", body: "Customers show a pickup code. Type it in and you're done." },
  { icon: ShieldCheck, title: "You stay in control", body: "Pause or remove a listing at any time. Approval keeps the platform trusted." },
];

function Providers() {
  return (
    <section id="providers" className="container-page scroll-mt-24 py-20 lg:py-24">
      <div className="relative overflow-hidden rounded-[2.5rem] bg-leaf-900 text-white shadow-lift">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.1fr]">
          <div className="relative min-h-72 sm:min-h-96 lg:min-h-full">
            <Photo photo={PHOTOS.canteenServing} sizes="(min-width: 1024px) 46vw, 100vw" className="absolute inset-0" />
            <div className="absolute inset-0 bg-gradient-to-t from-leaf-900/70 via-transparent to-transparent lg:bg-gradient-to-r lg:from-transparent lg:via-transparent lg:to-leaf-900/40" />
            <div className="absolute bottom-5 left-5 hidden w-40 overflow-hidden rounded-2xl shadow-lift ring-4 ring-leaf-900 sm:block lg:bottom-8 lg:left-8 lg:w-48">
              <div className="aspect-[4/3]">
                <Photo photo={PHOTOS.chefKitchen} sizes="192px" alt="" />
              </div>
            </div>
          </div>
          <div className="p-8 sm:p-12 lg:p-14">
            <p className="text-xs font-bold tracking-[0.14em] text-turmeric-300 uppercase">For canteens, cafeterias &amp; messes</p>
            <h2 className="mt-3 text-3xl text-white sm:text-[2.5rem] sm:leading-tight">
              Turn today's surplus into tomorrow's regulars.
            </h2>
            <p className="mt-4 max-w-xl text-[16px] leading-relaxed text-leaf-100">
              FoodLoop gives your kitchen a simple way to offer safe, unsold food to students and staff nearby,
              without changing how you cook or take payment.
            </p>
            <ul className="mt-8 grid grid-cols-1 gap-5 sm:grid-cols-2">
              {PROVIDER_BENEFITS.map((benefit) => (
                <li key={benefit.title} className="flex gap-3">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/10 text-turmeric-300 ring-1 ring-white/15">
                    <benefit.icon className="size-5" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="font-semibold text-white">{benefit.title}</p>
                    <p className="mt-0.5 text-[14px] leading-relaxed text-leaf-100/90">{benefit.body}</p>
                  </div>
                </li>
              ))}
            </ul>
            <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Link to="/register/kitchen" className="btn-accent btn-lg">
                Become a Partner <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
              <Link to="/#safety" className="btn btn-lg text-white hover:bg-white/10">
                How approval works
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ClosingCta() {
  return (
    <section className="container-page pt-20 sm:pt-24">
      <div className="card grid grid-cols-1 items-center gap-8 overflow-hidden p-8 sm:p-12 lg:grid-cols-[1.4fr_1fr]">
        <div>
          <h2 className="text-3xl sm:text-4xl">Hungry? See what's available nearby.</h2>
          <p className="mt-3 max-w-xl text-[16px] text-ink-600">
            Browse meals from approved kitchens, reserve in seconds and pay at the counter.
          </p>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <Link to="/meals" className="btn-primary btn-lg">
              <UtensilsCrossed className="size-4" aria-hidden="true" /> Explore Meals
            </Link>
            <Link to="/register" className="btn-secondary btn-lg">
              Create free account
            </Link>
          </div>
        </div>
        <div className="relative mx-auto hidden h-44 w-72 sm:block" aria-hidden="true">
          {[PHOTOS.masalaChai, PHOTOS.biryaniPan, PHOTOS.idliVada].map((item, index) => (
            <div
              key={item.slug}
              className="absolute top-1/2 size-36 -translate-y-1/2 overflow-hidden rounded-full shadow-lift ring-[6px] ring-white"
              style={{ left: `${index * 72}px`, zIndex: index === 1 ? 2 : 1 }}
            >
              <Photo photo={item} sizes="144px" alt="" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function LandingPage() {
  const { data, isLoading, error, refetch } = useAllListings();
  const live = (data ?? []).filter((listing) => listing.availability === "available");
  return (
    <>
      <Hero live={live} />
      <Categories live={live} />
      <ClosingSoon live={live} isLoading={isLoading} error={error} retry={() => refetch()} />
      <MenuPreview live={live} />
      <HowItWorks />
      <Kitchens live={live} />
      <Safety />
      <Sustainability />
      <Providers />
      <FaqPreview />
      <ClosingCta />
    </>
  );
}
