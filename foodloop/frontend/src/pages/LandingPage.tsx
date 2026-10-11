import {
  ArrowRight,
  BadgeCheck,
  ChefHat,
  CircleCheck,
  Clock,
  Hourglass,
  Recycle,
  ShieldCheck,
  Store,
  Ticket,
  Utensils,
  Wheat,
} from "lucide-react";
import { Link } from "react-router";

import { useListings } from "../api/queries";
import { ListingCard, ListingCardSkeleton } from "../components/ListingCard";
import { EmptyState } from "../components/ui";
import { MEAL_ILLUSTRATIONS } from "../lib/meals";

function HeroArt() {
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[520px]" aria-hidden="true">
      <div className="absolute inset-[6%] rounded-full bg-[radial-gradient(circle_at_50%_45%,var(--color-leaf-100),transparent_70%)]" />
      <img
        src={MEAL_ILLUSTRATIONS.dinner}
        alt=""
        className="absolute top-[4%] right-[2%] w-[58%] rotate-[7deg] rounded-[2rem] shadow-lift ring-8 ring-white"
      />
      <img
        src={MEAL_ILLUSTRATIONS.lunch}
        alt=""
        className="absolute bottom-[10%] left-[2%] w-[70%] -rotate-[4deg] rounded-[2rem] shadow-lift ring-8 ring-white"
      />
      <div className="absolute top-[14%] left-[0%] animate-float rounded-2xl bg-white p-3.5 pr-5 shadow-lift">
        <p className="text-[11px] font-bold tracking-wider text-ink-500 uppercase">Example listing</p>
        <p className="font-display mt-0.5 text-[15px] font-semibold">Veg thali</p>
        <p className="mt-0.5 text-sm">
          <span className="font-bold text-leaf-700">₹40</span>{" "}
          <span className="text-ink-500 line-through">₹80</span>
        </p>
      </div>
      <div
        className="absolute right-[0%] bottom-[18%] animate-float rounded-2xl bg-ink-900 px-4 py-3 text-white shadow-lift"
        style={{ animationDelay: "1.2s" }}
      >
        <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-white/70 uppercase">
          <Ticket className="size-3.5" /> Pickup code
        </p>
        <p className="mt-0.5 font-mono text-xl font-bold tracking-[0.2em]">K7Q2MX</p>
      </div>
      <div
        className="absolute right-[12%] bottom-[2%] animate-float rounded-full bg-white px-4 py-2 text-sm font-semibold shadow-lift"
        style={{ animationDelay: "2.4s" }}
      >
        <span className="flex items-center gap-1.5 text-saffron-600">
          <Clock className="size-4" /> Eat by 4:15 pm
        </span>
      </div>
    </div>
  );
}

const STEPS = [
  {
    icon: Store,
    title: "Kitchens list what's left",
    body: "After service, an approved canteen or mess lists safe surplus with its price, prepared time, allergens and an eat-by time.",
  },
  {
    icon: Ticket,
    title: "You reserve in seconds",
    body: "Pick a meal and quantity. You get a pickup code straight away. Pay the kitchen at the counter, by UPI or cash.",
  },
  {
    icon: Utensils,
    title: "Collect and enjoy",
    body: "Show your code within the pickup window. The kitchen hands over your meal, and good food doesn't go to waste.",
  },
];

const SAFETY = [
  {
    icon: BadgeCheck,
    title: "Approved kitchens only",
    body: "Every kitchen gives us its FSSAI registration, and we check it before it can list anything. An expired registration stops all sales automatically.",
  },
  {
    icon: Hourglass,
    title: "Expired food can't be sold",
    body: "Every meal has a pickup deadline and an eat-by time. FoodLoop checks the clock at the moment you reserve, so late food can never be bought.",
  },
  {
    icon: Wheat,
    title: "Allergens declared every time",
    body: "Kitchens must state the allergens and veg/non-veg status of every batch, and any shared-kitchen risk.",
  },
  {
    icon: ShieldCheck,
    title: "Kept hot, cold or shelf-stable",
    body: "Kitchens confirm how the food was stored. Food at room temperature gets a much shorter window than food kept hot or chilled.",
  },
];

function LiveMeals() {
  const { data, isLoading, isError } = useListings({ limit: 3, sort: "ending_soon" });
  if (isLoading) {
    return (
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((key) => (
          <ListingCardSkeleton key={key} />
        ))}
      </div>
    );
  }
  if (isError || !data || data.items.length === 0) {
    return (
      <div className="card">
        <EmptyState icon={<Utensils className="size-7" />} title="No meals listed right now">
          Kitchens usually post surplus after lunch and dinner service. Check back then, or create an account so
          you're ready to reserve.
        </EmptyState>
      </div>
    );
  }
  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {data.items.map((listing, index) => (
        <ListingCard key={listing.id} listing={listing} index={index} />
      ))}
    </div>
  );
}

export function LandingPage() {
  return (
    <>
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute -top-40 -right-40 size-[520px] rounded-full bg-saffron-100/60 blur-3xl" />
        <div className="pointer-events-none absolute top-60 -left-40 size-[420px] rounded-full bg-leaf-100/70 blur-3xl" />
        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-4 pt-10 pb-16 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-20 lg:pb-24">
          <div className="animate-rise">
            <p className="eyebrow">Surplus meals from canteens, messes &amp; PG kitchens</p>
            <h1 className="mt-5 text-[3.2rem] leading-[1.02] font-semibold text-ink-900 sm:text-7xl">
              Good food.
              <br />
              <span className="text-leaf-600 italic">Less waste.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-600">
              Reserve fresh, unsold meals from kitchens near you at a lower price, then pick them up before the
              deadline. Every kitchen is FSSAI-registered and approved by FoodLoop before it can list a single plate.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/meals" className="btn-primary min-h-12 px-6 text-[15px]">
                Find meals near you <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
              <Link to="/register/kitchen" className="btn-secondary min-h-12 px-6 text-[15px]">
                <ChefHat className="size-4" aria-hidden="true" /> List your kitchen's surplus
              </Link>
            </div>
            <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm font-medium text-ink-600">
              {["FSSAI-verified kitchens", "Allergens on every meal", "Pay at the counter"].map((item) => (
                <li key={item} className="flex items-center gap-1.5">
                  <CircleCheck className="size-4 text-leaf-600" aria-hidden="true" /> {item}
                </li>
              ))}
            </ul>
          </div>
          <HeroArt />
        </div>
      </section>

      <section className="border-y border-line/70 bg-cream-50">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
          <p className="eyebrow">How it works</p>
          <h2 className="mt-3 max-w-xl text-3xl font-semibold sm:text-4xl">Three steps from “still good” to dinner.</h2>
          <ol className="mt-10 grid gap-5 md:grid-cols-3">
            {STEPS.map((step, index) => (
              <li key={step.title} className="card relative p-6">
                <span className="font-display absolute top-5 right-6 text-5xl font-semibold text-cream-300">
                  {index + 1}
                </span>
                <div className="grid size-12 place-items-center rounded-2xl bg-leaf-600 text-white">
                  <step.icon className="size-6" aria-hidden="true" />
                </div>
                <h3 className="mt-5 text-xl font-semibold">{step.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-ink-600">{step.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Available now</p>
            <h2 className="mt-3 text-3xl font-semibold sm:text-4xl">Closing soon near you</h2>
          </div>
          <Link to="/meals" className="btn-secondary">
            See all meals <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
        <div className="mt-8">
          <LiveMeals />
        </div>
      </section>

      <section id="safety" className="scroll-mt-20 bg-cream-200/60">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
          <div className="max-w-2xl">
            <p className="eyebrow">Safe by design</p>
            <h2 className="mt-3 text-3xl font-semibold sm:text-4xl">Cheaper never means riskier.</h2>
            <p className="mt-4 text-lg leading-relaxed text-ink-600">
              Surplus food is only good if it's safe. These rules are enforced by the system itself, not left to
              chance.
            </p>
          </div>
          <div className="mt-10 grid gap-5 sm:grid-cols-2">
            {SAFETY.map((item) => (
              <div key={item.title} className="card flex gap-4 p-6">
                <div className="grid size-12 shrink-0 place-items-center rounded-2xl bg-leaf-50 text-leaf-700">
                  <item.icon className="size-6" aria-hidden="true" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold">{item.title}</h3>
                  <p className="mt-1.5 text-[15px] leading-relaxed text-ink-600">{item.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:py-20">
        <div className="relative overflow-hidden rounded-[2rem] bg-leaf-900 px-6 py-12 text-cream-100 sm:px-12 lg:px-16 lg:py-16">
          <Recycle className="pointer-events-none absolute -right-10 -bottom-10 size-72 text-leaf-800" aria-hidden="true" />
          <div className="relative grid gap-10 lg:grid-cols-[1.2fr_1fr] lg:items-center">
            <div>
              <p className="text-xs font-bold tracking-[0.14em] text-turmeric-300 uppercase">For kitchens</p>
              <h2 className="mt-3 text-3xl font-semibold text-white sm:text-4xl">
                Recover the cost of food you'd otherwise throw away.
              </h2>
              <p className="mt-4 max-w-xl text-lg leading-relaxed text-leaf-100">
                List surplus in under a minute, see reservations as they come in, and hand over food with a simple
                pickup code. You stay in control: pause or remove a listing at any time.
              </p>
              <Link to="/register/kitchen" className="btn mt-8 bg-turmeric-400 px-6 text-ink-900 hover:bg-turmeric-300">
                Register your kitchen <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </div>
            <ul className="space-y-3">
              {[
                "Free to try during the pilot",
                "FSSAI details verified before your first listing",
                "Customers pay you directly at the counter",
                "Simple daily numbers: listed, reserved, collected",
              ].map((item) => (
                <li key={item} className="flex items-start gap-3 rounded-2xl bg-white/5 px-4 py-3 ring-1 ring-white/10">
                  <CircleCheck className="mt-0.5 size-5 shrink-0 text-turmeric-300" aria-hidden="true" />
                  <span className="text-[15px] text-cream-100">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </>
  );
}
