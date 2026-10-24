import {
  ArrowRight,
  BadgeCheck,
  Check,
  ChefHat,
  CircleCheck,
  Clock,
  ExternalLink,
  Hourglass,
  IndianRupee,
  Leaf,
  Scale,
  ShieldCheck,
  Thermometer,
  Ticket,
  Timer,
  UtensilsCrossed,
  Wheat,
} from "lucide-react";
import { Link } from "react-router";

import { useListings } from "../api/queries";
import { ListingCard, ListingCardSkeleton } from "../components/ListingCard";
import { Photo } from "../components/Photo";
import { ErrorState, Notice } from "../components/ui";
import { CATEGORY_PHOTOS, PHOTOS } from "../lib/photos";

// ---------------------------------------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------------------------------------

function HeroVisual() {
  return (
    <div className="relative mx-auto w-full max-w-[560px] lg:max-w-none">
      <div
        aria-hidden="true"
        className="absolute -inset-3 rotate-[2.5deg] rounded-[2.5rem] bg-sage-200/80 sm:-inset-4 lg:-inset-5"
      />
      <div className="relative aspect-[4/3] overflow-hidden rounded-[2rem] shadow-lift ring-1 ring-black/5 sm:aspect-[5/4] lg:aspect-[4/5]">
        <Photo photo={PHOTOS.thaliSpread} priority sizes="(min-width: 1024px) 46vw, 92vw" />
      </div>

      {/* Example of what a listing looks like. Labelled as an example, not a live offer. */}
      <div
        aria-hidden="true"
        className="absolute -bottom-6 left-3 w-[236px] animate-float rounded-2xl bg-white/95 p-3 shadow-lift ring-1 ring-black/5 backdrop-blur sm:-left-8 sm:bottom-10 sm:w-[260px]"
      >
        <div className="flex gap-3">
          <div className="size-14 shrink-0 overflow-hidden rounded-xl sm:size-16">
            <Photo photo={PHOTOS.samosa} sizes="64px" alt="" />
          </div>
          <div className="min-w-0">
            <p className="text-[10.5px] font-bold tracking-wider text-saffron-600 uppercase">Example listing</p>
            <p className="truncate text-[14px] font-semibold text-ink-900">Samosa plate (2 pcs)</p>
            <p className="text-[14px]">
              <span className="font-bold text-leaf-700">₹15</span> <span className="text-ink-500 line-through">₹30</span>
            </p>
          </div>
        </div>
        <div className="mt-2.5 flex items-center justify-between rounded-xl bg-sage-50 px-3 py-2 text-[12px]">
          <span className="flex items-center gap-1.5 font-semibold text-ink-700">
            <Clock className="size-3.5 text-leaf-600" /> Pickup by 5:30 pm
          </span>
          <span className="font-semibold text-leaf-700">4 left</span>
        </div>
      </div>

      <div
        aria-hidden="true"
        className="absolute top-6 -right-1 animate-float rounded-2xl bg-leaf-900 px-4 py-3 text-white shadow-lift [animation-delay:1.6s] sm:-right-6 sm:top-10"
      >
        <p className="flex items-center gap-1.5 text-[10.5px] font-semibold tracking-wider text-leaf-200 uppercase">
          <Ticket className="size-3.5" /> Pickup code
        </p>
        <p className="mt-0.5 font-mono text-lg font-bold tracking-[0.22em] sm:text-xl">K7Q2MX</p>
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute top-[-14rem] right-[-12rem] hidden size-[44rem] rounded-full bg-sage-100/80 lg:block"
      />
      <div className="container-page relative grid items-center gap-12 pt-4 pb-20 sm:gap-14 sm:pt-10 lg:grid-cols-[1.02fr_1fr] lg:gap-16 lg:pt-12 lg:pb-24">
        <div className="relative z-10 animate-rise">
          <p className="inline-flex items-center gap-2 rounded-full border border-sage-200 bg-white/85 py-1.5 pr-3.5 pl-1.5 text-[13px] font-semibold text-leaf-800 shadow-soft backdrop-blur">
            <span className="grid size-6 place-items-center rounded-full bg-leaf-600 text-white">
              <Leaf className="size-3.5" aria-hidden="true" />
            </span>
            Surplus meals from campus &amp; city kitchens
          </p>
          <h1 className="mt-5 text-[2.6rem] leading-[1.03] text-ink-900 sm:mt-6 sm:text-6xl lg:text-[4.25rem]">
            Good food deserves{" "}
            <span className="relative inline-block text-leaf-600">
              another chance.
              <svg
                aria-hidden="true"
                viewBox="0 0 300 14"
                preserveAspectRatio="none"
                className="absolute -bottom-2 left-0 h-3 w-full text-saffron-400"
              >
                <path d="M2 9c60-6 130-8 296-3" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
              </svg>
            </span>
          </h1>
          <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-ink-700 sm:mt-7 sm:text-xl">
            Discover delicious surplus meals at lower prices while helping reduce food waste.
          </p>
          <p className="mt-3 hidden max-w-xl text-[15px] leading-relaxed text-ink-500 sm:block">
            Reserve from FSSAI-registered canteens, cafeterias, hostel messes and PG kitchens, then collect your meal
            before the pickup deadline.
          </p>
          <div className="mt-7 flex flex-col gap-3 sm:mt-9 sm:flex-row">
            <Link to="/meals" className="btn-primary btn-lg">
              Explore Meals <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
            <Link to="/register/kitchen" className="btn-secondary btn-lg">
              <ChefHat className="size-4" aria-hidden="true" /> Become a Partner
            </Link>
          </div>
          <ul className="mt-7 flex flex-wrap gap-x-5 gap-y-2.5 text-[13.5px] font-medium text-ink-700 sm:mt-10 sm:gap-x-6 sm:text-[14px]">
            {["FSSAI-verified kitchens", "Allergens on every meal", "Pay at the counter"].map((item) => (
              <li key={item} className="flex items-center gap-2">
                <span className="grid size-5 place-items-center rounded-full bg-leaf-100 text-leaf-700">
                  <Check className="size-3.5" strokeWidth={3} aria-hidden="true" />
                </span>
                {item}
              </li>
            ))}
          </ul>
        </div>
        <HeroVisual />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------
// Browse by craving + featured meals (real API data)
// ---------------------------------------------------------------------------------------------------------

function Cravings() {
  return (
    <section aria-labelledby="cravings-title" className="container-page">
      <div className="flex items-end justify-between gap-4">
        <h2 id="cravings-title" className="text-2xl sm:text-[1.75rem]">
          Browse by meal
        </h2>
        <Link to="/meals" className="text-sm font-semibold text-leaf-700 underline-offset-4 hover:underline">
          See everything
        </Link>
      </div>
      <ul className="mt-6 grid grid-cols-3 gap-x-3 gap-y-6 sm:grid-cols-6 sm:gap-5">
        {CATEGORY_PHOTOS.map((category) => (
          <li key={category.mealType}>
            <Link to={`/meals?meal=${category.mealType}`} className="group flex flex-col items-center gap-3 rounded-2xl text-center">
              <span className="block aspect-square w-full max-w-[148px] overflow-hidden rounded-full shadow-soft ring-4 ring-white transition duration-300 group-hover:-translate-y-1 group-hover:shadow-lift">
                <Photo photo={category.photo} sizes="(min-width: 640px) 148px, 30vw" className="transition duration-700 group-hover:scale-110" />
              </span>
              <span className="text-[13.5px] font-semibold text-ink-700 group-hover:text-leaf-700 sm:text-[14.5px]">
                {category.label}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EmptyMeals() {
  return (
    <div className="card grid items-center gap-8 overflow-hidden p-6 sm:p-10 md:grid-cols-[1fr_1.2fr]">
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
          <Link to="/meals" className="btn-secondary">
            Explore meals
          </Link>
        </div>
      </div>
    </div>
  );
}

function FeaturedMeals() {
  const { data, isLoading, isError, error, refetch } = useListings({ limit: 6, sort: "ending_soon" });
  const hasSample = data?.items.some((listing) => listing.provider.is_sample);
  return (
    <section aria-labelledby="featured-title" className="container-page mt-20 sm:mt-24">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Available now</p>
          <h2 id="featured-title" className="mt-2 text-3xl sm:text-4xl">
            Fresh surplus near you
          </h2>
          <p className="mt-2 max-w-xl text-[15px] text-ink-600">
            Live listings from approved kitchens, closing soonest first. Prices are set by each kitchen.
          </p>
        </div>
        <Link to="/meals" className="btn-secondary">
          Explore all meals <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </div>
      {hasSample && (
        <Notice tone="info" className="mt-6">
          These are <strong>sample listings</strong> for demonstration. The kitchens, meals and prices aren't real.
        </Notice>
      )}
      <div className="mt-8">
        {isLoading ? (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((key) => (
              <ListingCardSkeleton key={key} />
            ))}
          </div>
        ) : isError ? (
          <div className="card">
            <ErrorState error={error} onRetry={() => refetch()} />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyMeals />
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((listing, index) => (
              <div key={listing.id} className={index >= 3 ? "hidden sm:contents" : "contents"}>
                <ListingCard listing={listing} index={index} />
              </div>
            ))}
          </div>
        )}
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
    <section id="how-it-works" className="mt-24 scroll-mt-24 border-y border-line/70 bg-white">
      <div className="container-page py-20 lg:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">How it works</p>
          <h2 className="mt-3 text-3xl sm:text-[2.6rem] sm:leading-tight">From surplus to your plate in three steps</h2>
          <p className="mt-4 text-[16px] text-ink-600">
            No delivery fees, no waiting around. Just good food collected straight from the kitchen.
          </p>
        </div>
        <ol className="mt-14 grid gap-6 md:grid-cols-3">
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
      <div className="grid gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
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
        <div className="grid gap-4 sm:grid-cols-2">
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
      <div className="container-page grid gap-12 py-20 lg:grid-cols-[0.95fr_1.05fr] lg:items-center lg:gap-16 lg:py-24">
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
          <dl className="mt-8 grid gap-4 sm:grid-cols-2">
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
        <div className="grid lg:grid-cols-[1fr_1.1fr]">
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
            <ul className="mt-8 grid gap-5 sm:grid-cols-2">
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
    <section className="container-page">
      <div className="card grid items-center gap-8 overflow-hidden p-8 sm:p-12 lg:grid-cols-[1.4fr_1fr]">
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
  return (
    <>
      <Hero />
      <Cravings />
      <FeaturedMeals />
      <HowItWorks />
      <Safety />
      <Sustainability />
      <Providers />
      <ClosingCta />
    </>
  );
}
