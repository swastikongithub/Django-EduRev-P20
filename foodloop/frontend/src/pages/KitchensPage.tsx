import { ArrowLeft, BadgeCheck, ChefHat, Clock, MapPin, Store, Utensils } from "lucide-react";
import { Link, useParams } from "react-router";

import { useAllListings, useKitchenProfile, useKitchens, useListings, useMeta } from "../api/queries";
import type { Listing } from "../api/types";
import { KitchenCard } from "../components/KitchenCard";
import { ListingCard, ListingCardSkeleton } from "../components/ListingCard";
import { LiveDot, Rail, Reveal } from "../components/Live";
import { Photo } from "../components/Photo";
import { EmptyState, ErrorState, Notice, PageHeader, SampleBadge, Skeleton } from "../components/ui";
import { formatRupees, plural } from "../lib/format";
import { collagePhotos } from "../lib/photos";

const cleanName = (name: string) => name.replace(/^\[SAMPLE\]\s*/, "");

function useDishesByKitchen() {
  const { data } = useAllListings();
  const byKitchen = new Map<string, Listing[]>();
  for (const listing of data ?? []) {
    if (listing.availability !== "available") continue;
    byKitchen.set(listing.provider.slug, [...(byKitchen.get(listing.provider.slug) ?? []), listing]);
  }
  return byKitchen;
}

/** Every approved kitchen, with what each has on offer right now. */
export function KitchensPage() {
  const { data: kitchens, isLoading, isError, error, refetch } = useKitchens();
  const dishes = useDishesByKitchen();
  const hasSample = kitchens?.some((kitchen) => kitchen.is_sample);
  return (
    <div>
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <Store className="size-4" aria-hidden="true" /> Kitchens on FoodLoop
          </span>
        }
        title="Cooked by kitchens you can trust"
        description="Canteens, cafeterias, hostel messes and PG kitchens. Every one is FSSAI-registered and approved by FoodLoop before it can list food."
        actions={
          <Link to="/register/kitchen" className="btn-primary">
            <ChefHat className="size-4" aria-hidden="true" /> List your kitchen
          </Link>
        }
      />
      <div className="container-page py-10">
        {hasSample && (
          <Notice tone="info" className="mb-8">
            Kitchens marked <strong>Sample data</strong> are made up for demonstration. They aren't real businesses.
          </Notice>
        )}
        {isLoading ? (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-96 rounded-[1.25rem]" />
            ))}
          </div>
        ) : isError ? (
          <div className="card">
            <ErrorState error={error} onRetry={() => refetch()} />
          </div>
        ) : !kitchens?.length ? (
          <div className="card">
            <EmptyState
              icon={<Store className="size-7" />}
              title="No kitchens yet"
              action={
                <Link to="/register/kitchen" className="btn-primary">
                  Register your kitchen
                </Link>
              }
            >
              Run a canteen, mess or PG kitchen? Be the first to list your surplus.
            </EmptyState>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {kitchens.map((kitchen, index) => (
              <Reveal key={kitchen.id} delay={index * 60} className="flex [&>a]:w-full">
                <KitchenCard kitchen={kitchen} dishes={dishes.get(kitchen.slug) ?? []} />
              </Reveal>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** One kitchen's page: who they are, where to collect, and everything they have on offer right now. */
export function KitchenPage() {
  const { slug = "" } = useParams();
  const { data: meta } = useMeta();
  const { data: kitchen, isLoading, isError, error, refetch } = useKitchenProfile(slug);
  const listings = useListings({ kitchen: slug, limit: 60, sort: "ending_soon" });
  const { data: kitchens } = useKitchens();
  const dishes = useDishesByKitchen();

  if (isLoading) {
    return (
      <div className="container-page py-10">
        <Skeleton className="h-72 w-full rounded-[2rem]" />
      </div>
    );
  }
  if (isError || !kitchen) {
    return (
      <div className="container-page py-12">
        <div className="card">
          <ErrorState error={error} onRetry={() => refetch()} />
        </div>
        <div className="mt-6 text-center">
          <Link to="/kitchens" className="btn-secondary">
            <ArrowLeft className="size-4" aria-hidden="true" /> All kitchens
          </Link>
        </div>
      </div>
    );
  }

  const meals = listings.data?.items ?? [];
  const cover = collagePhotos(meals);
  const others = (kitchens ?? []).filter((other) => other.slug !== kitchen.slug);

  return (
    <div>
      <section className="relative overflow-hidden bg-leaf-900 text-white">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0">
          <div className="absolute -top-40 -right-20 size-[30rem] rounded-full bg-saffron-500/20 blur-3xl" />
          <div className="absolute inset-0 bg-[radial-gradient(rgb(255_255_255/0.06)_1px,transparent_1.3px)] [background-size:22px_22px]" />
        </div>
        <div className="container-page relative grid grid-cols-1 gap-10 py-10 sm:py-14 lg:grid-cols-[1.1fr_1fr] lg:items-center">
          <div className="animate-rise">
            <Link to="/kitchens" className="inline-flex items-center gap-1.5 text-[13.5px] font-semibold text-white/75 hover:text-white">
              <ArrowLeft className="size-4" aria-hidden="true" /> All kitchens
            </Link>
            <p className="mt-5 flex flex-wrap items-center gap-2 text-xs font-bold tracking-[0.14em] text-turmeric-300 uppercase">
              {meta?.labels.provider_kind[kitchen.kind]}
              {kitchen.is_sample && <SampleBadge />}
            </p>
            <h1 className="mt-2 text-[2.4rem] leading-tight text-white sm:text-5xl">{cleanName(kitchen.name)}</h1>
            {kitchen.description && <p className="mt-4 max-w-xl text-[16px] leading-relaxed text-white/80">{kitchen.description}</p>}
            <dl className="mt-7 grid grid-cols-1 max-w-xl gap-3 sm:grid-cols-2">
              <div className="glass rounded-2xl px-4 py-3">
                <dt className="flex items-center gap-1.5 text-[12.5px] text-white/65">
                  <LiveDot /> On offer now
                </dt>
                <dd className="font-display mt-0.5 text-2xl font-bold">
                  {plural(kitchen.live_meals, "meal")}
                  {kitchen.lowest_price_paise !== null && (
                    <span className="ml-2 text-[15px] font-semibold text-turmeric-300">from {formatRupees(kitchen.lowest_price_paise)}</span>
                  )}
                </dd>
              </div>
              <div className="glass rounded-2xl px-4 py-3">
                <dt className="flex items-center gap-1.5 text-[12.5px] text-white/65">
                  <BadgeCheck className="size-3.5" aria-hidden="true" /> {meta?.labels.fssai_kind[kitchen.fssai_kind] ?? "FSSAI"}
                </dt>
                <dd className="mt-1 font-mono text-[15px] font-semibold tracking-wide">{kitchen.fssai_number}</dd>
              </div>
            </dl>
          </div>
          <div className="grid h-64 grid-cols-[1.5fr_1fr] grid-rows-2 gap-3 sm:h-80" aria-hidden="true">
            {cover.map((photo, index) => (
              <div key={`${photo.slug}-${index}`} className={`overflow-hidden rounded-[1.4rem] shadow-lift ring-1 ring-white/10 ${index === 0 ? "row-span-2" : ""}`}>
                <Photo photo={photo} alt="" sizes={index === 0 ? "(min-width: 1024px) 28vw, 55vw" : "(min-width: 1024px) 18vw, 35vw"} priority={index === 0} />
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="container-page py-10">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="card flex gap-3 p-5">
            <MapPin className="mt-0.5 size-5 shrink-0 text-leaf-600" aria-hidden="true" />
            <div>
              <p className="font-semibold">Where to collect</p>
              <p className="mt-0.5 text-[14.5px] text-ink-600">
                {kitchen.address_line}, {kitchen.area}, {kitchen.city} {kitchen.pincode}
              </p>
            </div>
          </div>
          <div className="card flex gap-3 p-5">
            <Clock className="mt-0.5 size-5 shrink-0 text-leaf-600" aria-hidden="true" />
            <div>
              <p className="font-semibold">At the counter</p>
              <p className="mt-0.5 text-[14.5px] text-ink-600">
                {kitchen.pickup_instructions || "Show your pickup code at the counter."} Pay the kitchen directly when you collect.
              </p>
            </div>
          </div>
        </div>

        <section className="mt-12" aria-labelledby="kitchen-menu-title">
          <h2 id="kitchen-menu-title" className="flex items-center gap-2 text-3xl">
            <Utensils className="size-6 text-leaf-600" aria-hidden="true" /> On the menu now
          </h2>
          <div className="mt-6">
            {listings.isLoading ? (
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {[0, 1, 2].map((key) => (
                  <ListingCardSkeleton key={key} />
                ))}
              </div>
            ) : listings.isError ? (
              <div className="card">
                <ErrorState error={listings.error} onRetry={() => listings.refetch()} />
              </div>
            ) : meals.length === 0 ? (
              <div className="card">
                <EmptyState icon={<Utensils className="size-7" />} title="Nothing on offer right now">
                  This kitchen usually lists surplus after meal service. Check back later, or see other kitchens.
                </EmptyState>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {meals.map((listing, index) => (
                  <ListingCard key={listing.id} listing={listing} index={index} />
                ))}
              </div>
            )}
          </div>
        </section>

        {others.length > 0 && (
          <section className="mt-16" aria-labelledby="other-kitchens-title">
            <h2 id="other-kitchens-title" className="text-2xl">
              More kitchens
            </h2>
            <div className="mt-6">
              <Rail label="More kitchens">
                {others.map((other) => (
                  <div key={other.id} className="flex w-[285px] shrink-0 snap-start sm:w-[330px] [&>a]:w-full">
                    <KitchenCard kitchen={other} dishes={dishes.get(other.slug) ?? []} />
                  </div>
                ))}
              </Rail>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
