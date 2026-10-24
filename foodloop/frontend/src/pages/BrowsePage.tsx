import { Search, SlidersHorizontal, UtensilsCrossed, X } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { useListings, useMeta } from "../api/queries";
import type { Diet, MealType } from "../api/types";
import { ListingCard, ListingCardSkeleton } from "../components/ListingCard";
import { Photo } from "../components/Photo";
import { DietMark, ErrorState, Notice } from "../components/ui";
import { ALLERGEN_KEYS } from "../lib/meals";
import { CATEGORY_PHOTOS, PHOTOS } from "../lib/photos";

const DIETS: Diet[] = ["veg", "vegan", "egg", "non_veg"];
const PRICE_CAPS = [30, 50, 80, 120];
const AVAILABILITY = [
  { value: "available", label: "Can reserve" },
  { value: "pickup_now", label: "Pickup open now" },
  { value: "all", label: "Include sold out" },
];

function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <fieldset>
      <legend className="mb-2 text-[12px] font-bold tracking-[0.08em] text-ink-500 uppercase">{label}</legend>
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  );
}

export function BrowsePage() {
  const [params, setParams] = useSearchParams();
  const { data: meta } = useMeta();
  const [showFilters, setShowFilters] = useState(false);

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

  // Removable pills for every active filter.
  const pills: { key: string; label: string; onRemove: () => void }[] = [
    ...(q ? [{ key: "q", label: `“${q}”`, onRemove: () => update({ q: null }) }] : []),
    ...meals.map((meal) => ({
      key: `meal-${meal}`,
      label: CATEGORY_PHOTOS.find((item) => item.mealType === meal)?.label ?? meal,
      onRemove: () => toggle("meal", meals, meal),
    })),
    ...diets.map((diet) => ({
      key: `diet-${diet}`,
      label: meta?.labels.diet[diet as Diet] ?? diet,
      onRemove: () => toggle("diet", diets, diet),
    })),
    ...(max ? [{ key: "max", label: `Up to ₹${max}`, onRemove: () => update({ max: null }) }] : []),
    ...(availability !== "available"
      ? [{ key: "av", label: AVAILABILITY.find((a) => a.value === availability)?.label ?? availability, onRemove: () => update({ availability: null }) }]
      : []),
    ...avoid.map((allergen) => ({
      key: `avoid-${allergen}`,
      label: `No ${(meta?.labels.allergen[allergen] ?? allergen).split(" (")[0].toLowerCase()}`,
      onRemove: () => toggle("avoid", avoid, allergen),
    })),
  ];
  const clearAll = () => {
    setSearch("");
    setParams(sort !== "ending_soon" ? { sort } : {}, { replace: true });
  };
  const hasSample = data?.items.some((listing) => listing.provider.is_sample);

  const filterPanel = (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
      <FilterGroup label="Price">
        <button type="button" className="chip" aria-pressed={!max} onClick={() => update({ max: null })}>
          Any price
        </button>
        {PRICE_CAPS.map((cap) => (
          <button key={cap} type="button" className="chip" aria-pressed={max === String(cap)} onClick={() => update({ max: String(cap) })}>
            Up to ₹{cap}
          </button>
        ))}
      </FilterGroup>
      <FilterGroup label="Availability">
        {AVAILABILITY.map((option) => (
          <button
            key={option.value}
            type="button"
            className="chip"
            aria-pressed={availability === option.value}
            onClick={() => update({ availability: option.value === "available" ? null : option.value })}
          >
            {option.label}
          </button>
        ))}
      </FilterGroup>
      <FilterGroup label="Diet">
        {DIETS.map((diet) => (
          <button key={diet} type="button" className="chip" aria-pressed={diets.includes(diet)} onClick={() => toggle("diet", diets, diet)}>
            <DietMark diet={diet} />
            {meta?.labels.diet[diet] ?? diet}
          </button>
        ))}
      </FilterGroup>
      <FilterGroup label="Avoid allergens">
        {ALLERGEN_KEYS.slice(0, 7).map((allergen) => (
          <button key={allergen} type="button" className="chip" aria-pressed={avoid.includes(allergen)} onClick={() => toggle("avoid", avoid, allergen)}>
            {(meta?.labels.allergen[allergen] ?? allergen).split(" (")[0]}
          </button>
        ))}
      </FilterGroup>
    </div>
  );

  return (
    <div>
      <section className="border-b border-line/70 bg-sage-50">
        <div className="container-page pt-8 pb-7 sm:pt-12">
          <p className="eyebrow">Explore meals</p>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="text-[2.2rem] leading-tight sm:text-5xl">Good food, ready for pickup</h1>
              <p className="mt-2 max-w-2xl text-[15.5px] text-ink-600">
                Surplus from approved kitchens near you, priced to move. Reserve now and collect before the window closes.
              </p>
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <label className="relative flex-1">
              <span className="sr-only">Search meals, kitchens or areas</span>
              <Search className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-ink-500" aria-hidden="true" />
              <input
                type="search"
                className="input min-h-13 rounded-full border-white pl-12 text-[15.5px] shadow-soft"
                placeholder="Search thali, biryani, a kitchen or your area…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <div className="flex gap-3">
              <label className="flex-1 sm:w-52">
                <span className="sr-only">Sort meals</span>
                <select
                  className="input min-h-13 rounded-full border-white px-5 shadow-soft"
                  value={sort}
                  onChange={(event) => update({ sort: event.target.value === "ending_soon" ? null : event.target.value })}
                >
                  <option value="ending_soon">Closing soonest</option>
                  <option value="price_low">Lowest price</option>
                  <option value="discount">Biggest discount</option>
                  <option value="newest">Newest</option>
                </select>
              </label>
              <button
                type="button"
                className="btn-secondary min-h-13 shrink-0 border-white shadow-soft lg:hidden"
                aria-expanded={showFilters}
                aria-controls="filter-panel"
                onClick={() => setShowFilters((value) => !value)}
              >
                <SlidersHorizontal className="size-4" aria-hidden="true" /> Filters
                {pills.length > 0 && <span className="rounded-full bg-leaf-600 px-1.5 text-[11px] leading-[18px] text-white">{pills.length}</span>}
              </button>
            </div>
          </div>

          <div className="-mx-4 mt-6 flex gap-3 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:px-0" role="group" aria-label="Meal categories">
            <button
              type="button"
              aria-pressed={meals.length === 0}
              onClick={() => update({ meal: null })}
              className="group flex shrink-0 items-center gap-2.5 rounded-full border border-line bg-white py-1.5 pr-4 pl-1.5 text-[14px] font-semibold text-ink-700 shadow-soft transition hover:border-leaf-200 aria-pressed:border-leaf-600 aria-pressed:bg-leaf-600 aria-pressed:text-white"
            >
              <span className="grid size-9 place-items-center rounded-full bg-sage-100 text-leaf-700 group-aria-pressed:bg-white/15 group-aria-pressed:text-white">
                <UtensilsCrossed className="size-4" aria-hidden="true" />
              </span>
              All meals
            </button>
            {CATEGORY_PHOTOS.map((category) => (
              <button
                key={category.mealType}
                type="button"
                aria-pressed={meals.includes(category.mealType)}
                onClick={() => toggle("meal", meals, category.mealType as MealType)}
                className="flex shrink-0 items-center gap-2.5 rounded-full border border-line bg-white py-1.5 pr-4 pl-1.5 text-[14px] font-semibold text-ink-700 shadow-soft transition hover:border-leaf-200 aria-pressed:border-leaf-600 aria-pressed:bg-leaf-600 aria-pressed:text-white"
              >
                <span className="size-9 overflow-hidden rounded-full">
                  <Photo photo={category.photo} sizes="36px" alt="" />
                </span>
                {category.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="container-page py-8">
        <div
          id="filter-panel"
          className={`${showFilters ? "block animate-fade" : "hidden"} card mb-6 p-5 sm:p-6 lg:block`}
          aria-label="Filters"
        >
          {filterPanel}
        </div>

        <div className="flex min-h-9 flex-wrap items-center gap-2" aria-live="polite">
          <p className="mr-2 text-[14px] text-ink-600">
            {data && !isLoading && (
              <>
                <span className="font-semibold text-ink-900">{data.total}</span> {data.total === 1 ? "meal" : "meals"}
                {isFetching && <span className="ml-2 text-ink-500">· updating…</span>}
              </>
            )}
          </p>
          {pills.map((pill) => (
            <button
              key={pill.key}
              type="button"
              onClick={pill.onRemove}
              className="inline-flex min-h-8 items-center gap-1.5 rounded-full bg-leaf-50 py-1 pr-2 pl-3 text-[13px] font-semibold text-leaf-800 ring-1 ring-leaf-100 transition hover:bg-leaf-100"
              aria-label={`Remove filter ${pill.label}`}
            >
              {pill.label} <X className="size-3.5" aria-hidden="true" />
            </button>
          ))}
          {pills.length > 0 && (
            <button type="button" className="text-[13px] font-semibold text-ink-600 underline-offset-4 hover:underline" onClick={clearAll}>
              Clear all
            </button>
          )}
        </div>

        {hasSample && (
          <Notice tone="info" className="mt-4">
            Showing <strong>sample listings</strong> for demonstration. The kitchens, meals and prices aren't real.
          </Notice>
        )}

        <div className="mt-6">
          {isLoading ? (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2, 3, 4, 5].map((key) => (
                <ListingCardSkeleton key={key} />
              ))}
            </div>
          ) : isError ? (
            <div className="card">
              <ErrorState error={error} onRetry={() => refetch()} />
            </div>
          ) : data && data.items.length > 0 ? (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {data.items.map((listing, index) => (
                <ListingCard key={listing.id} listing={listing} index={index} />
              ))}
            </div>
          ) : (
            <div className="card flex flex-col items-center px-6 py-14 text-center">
              <div className="relative h-24 w-48" aria-hidden="true">
                {[PHOTOS.samosa, PHOTOS.steelThali, PHOTOS.masalaChai].map((item, index) => (
                  <div
                    key={item.slug}
                    className="absolute top-0 size-24 overflow-hidden rounded-full opacity-90 shadow-soft ring-4 ring-white"
                    style={{ left: `${index * 48}px`, zIndex: index === 1 ? 2 : 1 }}
                  >
                    <Photo photo={item} sizes="96px" alt="" />
                  </div>
                ))}
              </div>
              <h2 className="mt-6 text-2xl">{pills.length ? "No meals match these filters" : "No meals listed right now"}</h2>
              <p className="mt-2 max-w-md text-[15px] leading-relaxed text-ink-600">
                {pills.length
                  ? "Try removing a filter or searching for something else."
                  : "Kitchens usually post surplus right after lunch and dinner service. This page refreshes on its own."}
              </p>
              {pills.length > 0 && (
                <button type="button" className="btn-primary mt-6" onClick={clearAll}>
                  Clear all filters
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
