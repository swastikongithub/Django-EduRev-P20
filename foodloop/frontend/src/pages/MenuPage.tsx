import { Search, UtensilsCrossed } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { useAllListings } from "../api/queries";
import type { Diet, Listing, MealType } from "../api/types";
import { LiveDot } from "../components/Live";
import { MenuRow } from "../components/MenuRow";
import { Photo } from "../components/Photo";
import { DietMark, EmptyState, ErrorState, Notice, Skeleton } from "../components/ui";
import { formatRupees } from "../lib/format";
import { CATEGORY_PHOTOS } from "../lib/photos";

type DietFilter = "all" | "veg" | "non_veg";
type SortBy = "price" | "closing";

const DIET_FILTERS: { value: DietFilter; label: string; diet?: Diet }[] = [
  { value: "all", label: "Everything" },
  { value: "veg", label: "Veg only", diet: "veg" },
  { value: "non_veg", label: "Non-veg", diet: "non_veg" },
];

function matchesDiet(listing: Listing, filter: DietFilter) {
  if (filter === "all") return true;
  if (filter === "veg") return listing.diet === "veg" || listing.diet === "vegan";
  return listing.diet === "non_veg" || listing.diet === "egg";
}

/** Today's menu: every dish that can be reserved right now, grouped like a restaurant menu, with prices. */
export function MenuPage() {
  const { data, isLoading, isError, error, refetch, dataUpdatedAt } = useAllListings();
  const [query, setQuery] = useState("");
  const [diet, setDiet] = useState<DietFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("price");

  const live = useMemo(() => (data ?? []).filter((listing) => listing.availability === "available"), [data]);
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return live
      .filter((listing) => matchesDiet(listing, diet))
      .filter(
        (listing) =>
          !needle ||
          [listing.title, listing.description, listing.provider.name, listing.provider.area].some((text) =>
            text.toLowerCase().includes(needle),
          ),
      )
      .sort((a, b) =>
        sortBy === "price" ? a.price_paise - b.price_paise : a.reservations_close_at.localeCompare(b.reservations_close_at),
      );
  }, [live, query, diet, sortBy]);

  const groups = CATEGORY_PHOTOS.map((category) => ({
    ...category,
    items: shown.filter((listing) => listing.meal_type === (category.mealType as MealType)),
  }));
  const hasSample = live.some((listing) => listing.provider.is_sample);
  const cheapest = live.length ? Math.min(...live.map((listing) => listing.price_paise)) : null;

  return (
    <div>
      <section className="relative overflow-hidden bg-night text-white">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0">
          <div className="absolute -top-40 right-0 size-[30rem] rounded-full bg-brand-500/20 blur-3xl" />
          <div className="absolute inset-0 bg-[radial-gradient(rgb(255_255_255/0.06)_1px,transparent_1.3px)] [background-size:22px_22px]" />
        </div>
        <div className="container-page relative py-10 sm:py-14">
          <p className="flex items-center gap-2 text-xs font-bold tracking-[0.14em] text-turmeric-300 uppercase">
            <LiveDot /> Live menu
          </p>
          <h1 className="mt-3 text-[2.4rem] leading-tight text-white sm:text-5xl">Today's menu</h1>
          <p className="mt-3 max-w-2xl text-[16px] text-white/80">
            {isLoading
              ? "Loading what's cooking…"
              : `${live.length} dishes from approved kitchens${cheapest !== null ? `, from ${formatRupees(cheapest)}` : ""}. Pay at the counter when you collect.`}
          </p>
          <div className="mt-7 flex flex-col gap-3 lg:flex-row lg:items-center">
            <label className="relative flex-1 lg:max-w-md">
              <span className="sr-only">Search the menu</span>
              <Search className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-fg-muted" aria-hidden="true" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search dishes or kitchens"
                className="input min-h-12 rounded-full border-transparent pl-12"
              />
            </label>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Diet">
              {DIET_FILTERS.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  aria-pressed={diet === filter.value}
                  onClick={() => setDiet(filter.value)}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-full bg-white/10 px-4 text-[13.5px] font-semibold text-white ring-1 ring-white/15 transition hover:bg-white/20 aria-pressed:bg-panel aria-pressed:text-fg"
                >
                  {filter.diet && <DietMark diet={filter.diet} />}
                  {filter.label}
                </button>
              ))}
            </div>
            <label className="lg:ml-auto">
              <span className="sr-only">Sort the menu</span>
              <select
                value={sortBy}
                onChange={(event) => setSortBy(event.target.value as SortBy)}
                className="input min-h-10 rounded-full border-transparent pr-9 text-[14px]"
              >
                <option value="price">Lowest price first</option>
                <option value="closing">Closing soonest first</option>
              </select>
            </label>
          </div>
        </div>
      </section>

      <nav
        aria-label="Menu sections"
        className="sticky top-[4.25rem] z-20 border-b border-line/70 bg-page/90 backdrop-blur-xl"
      >
        <div className="container-page rail gap-2 py-3">
          {groups.map((group) => (
            <a
              key={group.mealType}
              href={`#menu-${group.mealType}`}
              className="chip shrink-0 snap-start"
              aria-disabled={group.items.length === 0 || undefined}
            >
              {group.label}
              <span className="rounded-full bg-raised px-1.5 text-[11px] text-fg-soft">{group.items.length}</span>
            </a>
          ))}
        </div>
      </nav>

      <div className="container-page py-10">
        {hasSample && (
          <Notice tone="info" className="mb-8">
            Showing <strong>sample listings</strong> for demonstration. The kitchens, meals and prices aren't real.
          </Notice>
        )}
        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {Array.from({ length: 8 }, (_, key) => (
              <Skeleton key={key} className="h-20 rounded-2xl" />
            ))}
          </div>
        ) : isError ? (
          <div className="card">
            <ErrorState error={error} onRetry={() => refetch()} />
          </div>
        ) : shown.length === 0 ? (
          <div className="card">
            <EmptyState
              icon={<UtensilsCrossed className="size-7" />}
              title={live.length === 0 ? "Nothing on the menu right now" : "No dishes match"}
              action={
                live.length === 0 ? (
                  <Link to="/kitchens" className="btn-primary">
                    See the kitchens
                  </Link>
                ) : (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setQuery("");
                      setDiet("all");
                    }}
                  >
                    Show everything
                  </button>
                )
              }
            >
              {live.length === 0
                ? "Kitchens list surplus right after lunch and dinner service. Check back soon."
                : "Try another word, or switch the diet filter back to everything."}
            </EmptyState>
          </div>
        ) : (
          <div className="space-y-12">
            {groups
              .filter((group) => group.items.length > 0)
              .map((group) => (
                <section key={group.mealType} id={`menu-${group.mealType}`} className="scroll-mt-36" aria-labelledby={`menu-${group.mealType}-title`}>
                  <div className="flex items-center gap-4 border-b border-line pb-4">
                    <span className="size-14 shrink-0 overflow-hidden rounded-full shadow-soft ring-4 ring-panel">
                      <Photo photo={group.photo} sizes="56px" alt="" />
                    </span>
                    <div>
                      <h2 id={`menu-${group.mealType}-title`} className="text-2xl">
                        {group.label}
                      </h2>
                      <p className="text-[13.5px] text-fg-muted">
                        {group.items.length} {group.items.length === 1 ? "dish" : "dishes"} · from{" "}
                        {formatRupees(Math.min(...group.items.map((item) => item.price_paise)))}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-x-8 gap-y-1 md:grid-cols-2">
                    {group.items.map((listing) => (
                      <MenuRow key={listing.id} listing={listing} />
                    ))}
                  </div>
                </section>
              ))}
          </div>
        )}
        {dataUpdatedAt > 0 && !isError && (
          <p className="mt-12 flex items-center justify-center gap-2 text-center text-[13px] text-fg-muted">
            <LiveDot /> Prices and portions update by themselves every 30 seconds.
          </p>
        )}
      </div>
    </div>
  );
}
