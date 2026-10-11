import { Search, SlidersHorizontal, UtensilsCrossed, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { useListings, useMeta } from "../api/queries";
import type { Diet, MealType } from "../api/types";
import { ListingCard, ListingCardSkeleton } from "../components/ListingCard";
import { EmptyState, ErrorState } from "../components/ui";
import { ALLERGEN_KEYS } from "../lib/meals";

const MEAL_TYPES: MealType[] = ["breakfast", "lunch", "snacks", "dinner", "bakery", "beverages"];
const DIETS: Diet[] = ["veg", "vegan", "egg", "non_veg"];
const PRICE_CAPS = [30, 50, 80, 120];

export function BrowsePage() {
  const [params, setParams] = useSearchParams();
  const { data: meta } = useMeta();
  const [showMore, setShowMore] = useState(false);

  // Filters live in the URL, so a filtered view can be shared or bookmarked.
  const q = params.get("q") ?? "";
  const meals = params.getAll("meal");
  const diets = params.getAll("diet");
  const avoid = params.getAll("avoid");
  const max = params.get("max") ?? "";
  const availability = params.get("availability") ?? "available";
  const sort = params.get("sort") ?? "ending_soon";

  const [search, setSearch] = useState(q);
  useEffect(() => setSearch(q), [q]);
  useEffect(() => {
    const id = window.setTimeout(() => {
      if (search.trim() !== q) update({ q: search.trim() || null });
    }, 350);
    return () => window.clearTimeout(id);
  }, [search]);

  function update(changes: Record<string, string | string[] | null>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      next.delete(key);
      if (Array.isArray(value)) value.forEach((item) => next.append(key, item));
      else if (value) next.set(key, value);
    }
    setParams(next, { replace: true });
  }

  function toggle(key: string, current: string[], value: string) {
    update({ [key]: current.includes(value) ? current.filter((item) => item !== value) : [...current, value] });
  }

  const query = useMemo(
    () => ({
      q: q || undefined,
      meal_type: meals,
      diet: diets,
      exclude_allergen: avoid,
      max_price_paise: max ? Number(max) * 100 : undefined,
      availability,
      sort,
      limit: 48,
    }),
    [params],
  );
  const { data, isLoading, isError, error, refetch, isFetching } = useListings(query);
  const activeFilters = meals.length + diets.length + avoid.length + (max ? 1 : 0) + (q ? 1 : 0) + (availability !== "available" ? 1 : 0);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <header className="max-w-2xl">
        <p className="eyebrow">Browse</p>
        <h1 className="mt-2 text-4xl font-semibold sm:text-5xl">Meals available now</h1>
        <p className="mt-3 text-[15px] text-ink-600">
          Surplus from approved kitchens, priced to move. Reserve, then collect before the pickup window closes.
        </p>
      </header>

      <section aria-label="Search and filters" className="card mt-8 p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="relative flex-1">
            <span className="sr-only">Search meals or kitchens</span>
            <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4.5 -translate-y-1/2 text-ink-500" aria-hidden="true" />
            <input
              type="search"
              className="input pl-10"
              placeholder="Search thali, biryani, a kitchen or area…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <div className="flex gap-3">
            <label className="flex-1 sm:w-48">
              <span className="sr-only">Sort by</span>
              <select className="input" value={sort} onChange={(event) => update({ sort: event.target.value })}>
                <option value="ending_soon">Closing soonest</option>
                <option value="price_low">Lowest price</option>
                <option value="discount">Biggest discount</option>
                <option value="newest">Newest</option>
              </select>
            </label>
            <button
              type="button"
              className="btn-secondary shrink-0"
              aria-expanded={showMore}
              aria-controls="more-filters"
              onClick={() => setShowMore((value) => !value)}
            >
              <SlidersHorizontal className="size-4" aria-hidden="true" />
              <span className="hidden sm:inline">Filters</span>
              {activeFilters > 0 && (
                <span className="rounded-full bg-leaf-600 px-1.5 text-[11px] leading-[18px] text-white">{activeFilters}</span>
              )}
            </button>
          </div>
        </div>

        <div className="mt-4 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]" role="group" aria-label="Meal type">
          {MEAL_TYPES.map((meal) => (
            <button
              key={meal}
              type="button"
              className="chip shrink-0"
              aria-pressed={meals.includes(meal)}
              onClick={() => toggle("meal", meals, meal)}
            >
              {meta?.labels.meal_type[meal] ?? meal}
            </button>
          ))}
        </div>

        {showMore && (
          <div id="more-filters" className="mt-5 grid animate-rise gap-5 border-t border-line pt-5 md:grid-cols-3">
            <fieldset>
              <legend className="label">Diet</legend>
              <div className="flex flex-wrap gap-2">
                {DIETS.map((diet) => (
                  <button
                    key={diet}
                    type="button"
                    className="chip"
                    aria-pressed={diets.includes(diet)}
                    onClick={() => toggle("diet", diets, diet)}
                  >
                    {meta?.labels.diet[diet] ?? diet}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="grid grid-cols-2 gap-3">
              <label>
                <span className="label">Max price</span>
                <select className="input" value={max} onChange={(event) => update({ max: event.target.value || null })}>
                  <option value="">Any price</option>
                  {PRICE_CAPS.map((cap) => (
                    <option key={cap} value={cap}>
                      Up to ₹{cap}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="label">Show</span>
                <select
                  className="input"
                  value={availability}
                  onChange={(event) => update({ availability: event.target.value === "available" ? null : event.target.value })}
                >
                  <option value="available">Can reserve</option>
                  <option value="pickup_now">Pickup open now</option>
                  <option value="all">Include sold out</option>
                </select>
              </label>
            </div>
            <fieldset>
              <legend className="label">Avoid allergens</legend>
              <div className="flex flex-wrap gap-2">
                {ALLERGEN_KEYS.map((allergen) => (
                  <button
                    key={allergen}
                    type="button"
                    className="chip"
                    aria-pressed={avoid.includes(allergen)}
                    onClick={() => toggle("avoid", avoid, allergen)}
                  >
                    {(meta?.labels.allergen[allergen] ?? allergen).split(" (")[0]}
                  </button>
                ))}
              </div>
              <p className="hint">Based on what kitchens declare. If you have a severe allergy, confirm with the kitchen.</p>
            </fieldset>
          </div>
        )}
      </section>

      <div className="mt-6 flex min-h-8 items-center justify-between gap-3" aria-live="polite">
        <p className="text-sm text-ink-600">
          {data && !isLoading && (
            <>
              <span className="font-semibold text-ink-900">{data.total}</span> {data.total === 1 ? "meal" : "meals"}
              {isFetching && <span className="ml-2 text-ink-500">· updating…</span>}
            </>
          )}
        </p>
        {activeFilters > 0 && (
          <button type="button" className="btn-ghost btn-sm" onClick={() => setParams({}, { replace: true })}>
            <X className="size-4" aria-hidden="true" /> Clear filters
          </button>
        )}
      </div>

      <div className="mt-4">
        {isLoading ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((key) => (
              <ListingCardSkeleton key={key} />
            ))}
          </div>
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : data && data.items.length > 0 ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((listing, index) => (
              <ListingCard key={listing.id} listing={listing} index={index} />
            ))}
          </div>
        ) : (
          <div className="card">
            <EmptyState
              icon={<UtensilsCrossed className="size-7" />}
              title={activeFilters ? "No meals match these filters" : "No meals listed right now"}
              action={
                activeFilters ? (
                  <button type="button" className="btn-secondary" onClick={() => setParams({}, { replace: true })}>
                    Clear filters
                  </button>
                ) : undefined
              }
            >
              {activeFilters
                ? "Try removing a filter or searching for something else."
                : "Kitchens usually list surplus after lunch and dinner service. This page refreshes on its own."}
            </EmptyState>
          </div>
        )}
      </div>
    </div>
  );
}
