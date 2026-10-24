import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BadgeCheck,
  ChevronRight,
  CircleCheck,
  Clock,
  Flame,
  Hourglass,
  MapPin,
  Minus,
  Package,
  Plus,
  Snowflake,
  Store,
  Thermometer,
  Ticket,
  Wheat,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { api, ApiError, errorMessage } from "../api/client";
import { keys, useListing, useMe, useMeta } from "../api/queries";
import type { CustomerReservation, Listing, Storage } from "../api/types";
import { MealImage } from "../components/MealImage";
import { useToast } from "../components/Toast";
import { BusyLabel, DietMark, ErrorState, Notice, SampleBadge, Skeleton, StatusPill } from "../components/ui";
import { formatDateTime, formatRupees, formatTime, relativeTime } from "../lib/format";
import { useNow } from "../lib/useNow";
import { newId } from "../lib/uuid";

const STORAGE_ICONS: Record<Storage, typeof Flame> = {
  hot_held: Flame,
  refrigerated: Snowflake,
  room_temp: Thermometer,
  shelf_stable: Package,
};

const UNAVAILABLE_TEXT: Record<string, string> = {
  sold_out: "This meal has sold out. Check other meals nearby.",
  closed: "Reservations for this meal have closed because the pickup window is about to end.",
  expired: "This pickup window has ended. FoodLoop never sells food after its deadline.",
  unavailable: "This kitchen isn't taking reservations right now.",
};

function ReservePanel({ listing, onReserved }: { listing: Listing; onReserved: () => void }) {
  const { data: me } = useMe();
  const location = useLocation();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [quantity, setQuantity] = useState(1);
  // One id per "Reserve" attempt: if the request is sent twice (double tap, retry), only one reservation is made.
  const attemptKey = useRef(newId());
  const maxQuantity = Math.max(1, Math.min(listing.max_per_order, listing.quantity_available));

  const reserve = useMutation({
    mutationFn: () =>
      api<CustomerReservation>("/reservations", {
        method: "POST",
        body: { listing_id: listing.id, quantity, idempotency_key: attemptKey.current },
      }),
    onSuccess: () => {
      onReserved();
      toast.success("Reservation confirmed", "Show your pickup code at the counter.");
    },
    onError: (error) => toast.error("Couldn't reserve", errorMessage(error)),
    onSettled: (_data, error) => {
      // A definite answer (success or a business "no") ends this attempt; network failures keep the key for retry.
      if (!(error instanceof ApiError && error.status === 0)) attemptKey.current = newId();
      queryClient.invalidateQueries({ queryKey: keys.listing(listing.id) });
      queryClient.invalidateQueries({ queryKey: ["listings"] });
      queryClient.invalidateQueries({ queryKey: keys.myReservations });
    },
  });

  if (reserve.data) {
    const reservation = reserve.data;
    return (
      <div className="card animate-rise overflow-hidden">
        <div className="flex items-center gap-2 bg-leaf-600 px-5 py-4 font-semibold text-white">
          <CircleCheck className="size-5" aria-hidden="true" /> Reserved! Here's your pickup code
        </div>
        <div className="p-5">
          <p className="rounded-2xl border-2 border-dashed border-leaf-200 bg-leaf-50 py-4 text-center font-mono text-3xl font-bold tracking-[0.3em] text-leaf-800">
            {reservation.pickup_code}
          </p>
          <p className="mt-4 text-[15px] leading-relaxed text-ink-700">
            Show this code at <strong>{reservation.provider.name}</strong> by{" "}
            <strong>{formatTime(reservation.pickup_deadline)}</strong> and pay{" "}
            <strong>{formatRupees(reservation.total_paise)}</strong> at the counter.
          </p>
          <Link to="/reservations" className="btn-primary mt-5 w-full">
            <Ticket className="size-4" aria-hidden="true" /> View my reservations
          </Link>
        </div>
      </div>
    );
  }

  if (listing.availability !== "available") {
    return (
      <Notice tone="warning" title="Not available to reserve">
        {UNAVAILABLE_TEXT[listing.availability]}
      </Notice>
    );
  }

  return (
    <div className="card p-5 sm:p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <span id="qty-label" className="text-[15px] font-semibold">
            Portions
          </span>
          <p className="text-[13px] text-ink-500">
            Up to {listing.max_per_order} per order · {listing.quantity_available} left
          </p>
        </div>
        <div className="inline-flex items-center gap-1 rounded-full border border-line bg-cream-50 p-1" role="group" aria-labelledby="qty-label">
          <button
            type="button"
            className="grid size-10 place-items-center rounded-full bg-white shadow-soft transition hover:bg-leaf-50 disabled:opacity-40"
            onClick={() => setQuantity((value) => Math.max(1, value - 1))}
            disabled={quantity <= 1}
            aria-label="One fewer"
          >
            <Minus className="size-4" />
          </button>
          <output className="w-9 text-center text-lg font-semibold tabular-nums" aria-live="polite">
            {quantity}
          </output>
          <button
            type="button"
            className="grid size-10 place-items-center rounded-full bg-white shadow-soft transition hover:bg-leaf-50 disabled:opacity-40"
            onClick={() => setQuantity((value) => Math.min(maxQuantity, value + 1))}
            disabled={quantity >= maxQuantity}
            aria-label="One more"
          >
            <Plus className="size-4" />
          </button>
        </div>
      </div>
      <div className="mt-5 flex items-baseline justify-between border-t border-line pt-4">
        <span className="text-[14px] text-ink-600">Total, paid at pickup</span>
        <span className="font-display text-3xl font-bold">{formatRupees(listing.price_paise * quantity)}</span>
      </div>

      {reserve.isError && (
        <Notice tone="danger" className="mt-4">
          {errorMessage(reserve.error)}
        </Notice>
      )}

      {!me ? (
        <Link to={`/login?next=${encodeURIComponent(location.pathname)}`} className="btn-primary btn-lg mt-5 w-full">
          Log in to reserve
        </Link>
      ) : me.user.role !== "customer" ? (
        <Notice tone="info" className="mt-5">
          Reservations are made from customer accounts.
        </Notice>
      ) : (
        <button type="button" className="btn-primary btn-lg mt-5 w-full" disabled={reserve.isPending} onClick={() => reserve.mutate()}>
          <BusyLabel busy={reserve.isPending} busyText="Reserving…">
            Reserve {quantity} for {formatRupees(listing.price_paise * quantity)}
          </BusyLabel>
        </button>
      )}
      <p className="mt-3 text-center text-[12.5px] leading-snug text-ink-500">
        Free to cancel until the pickup window ends. If your plans change, please cancel so someone else can have it.
      </p>
    </div>
  );
}

/** True while the element is on screen. Used to hide the phone's bottom "Reserve" bar when the real panel is visible. */
function useOnScreen<T extends Element>() {
  const [element, setElement] = useState<T | null>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.2 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return [setElement, visible] as const;
}

function DetailSkeleton() {
  return (
    <div className="container-page py-8" aria-busy="true" aria-label="Loading meal">
      <Skeleton className="h-4 w-48" />
      <div className="mt-6 grid grid-cols-1 gap-10 lg:grid-cols-[1.2fr_1fr]">
        <Skeleton className="aspect-[4/3] w-full rounded-[2rem]" />
        <div className="space-y-4">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-10 w-4/5" />
          <Skeleton className="h-10 w-40" />
          <Skeleton className="h-56 w-full rounded-[1.25rem]" />
        </div>
      </div>
    </div>
  );
}

export function ListingDetailPage() {
  const { id = "" } = useParams();
  const { data: listing, isLoading, isError, error, refetch } = useListing(id);
  const { data: meta } = useMeta();
  const now = useNow();
  const [reserved, setReserved] = useState(false);
  const [reserveRef, reserveVisible] = useOnScreen<HTMLDivElement>();

  if (isLoading) return <DetailSkeleton />;
  if (isError || !listing) {
    return (
      <div className="container-page py-12">
        <div className="card">
          <ErrorState error={error} onRetry={() => refetch()} />
        </div>
        <div className="mt-6 text-center">
          <Link to="/meals" className="btn-secondary">
            <ArrowLeft className="size-4" aria-hidden="true" /> Back to meals
          </Link>
        </div>
      </div>
    );
  }

  const StorageIcon = STORAGE_ICONS[listing.storage];
  const available = listing.availability === "available";
  const photoLabel = !listing.image_url
    ? "Representative image, not the actual food"
    : listing.image_is_representative
      ? "Representative photo"
      : "Photo from the kitchen";

  return (
    <div className="pb-28 lg:pb-0">
      <div className="container-page py-6 sm:py-8">
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[13.5px] text-ink-500">
          <Link to="/meals" className="font-medium text-leaf-700 underline-offset-4 hover:underline">
            Explore meals
          </Link>
          <ChevronRight className="size-3.5" aria-hidden="true" />
          <span className="truncate" aria-current="page">
            {listing.title}
          </span>
        </nav>

        {/* Phones read photo → name, price, reserve → details; desktop puts the reserve column beside both. */}
        <div className="mt-5 grid grid-cols-1 gap-8 lg:grid-cols-[1.2fr_1fr] lg:grid-rows-[auto_1fr] lg:gap-x-12">
          <div className="animate-rise lg:col-start-1 lg:row-start-1">
            <div className="relative aspect-[4/3] overflow-hidden rounded-[2rem] bg-cream-200 shadow-soft">
              <MealImage
                imageUrl={listing.image_url}
                mealType={listing.meal_type}
                title={listing.title}
                seed={listing.id}
                alt={listing.title}
                sizes="(min-width: 1024px) 680px, 100vw"
              />
              <div className="absolute top-4 left-4 flex gap-2">
                {listing.discount_percent > 0 && (
                  <span className="badge bg-saffron-600 px-3 py-1 text-[13px] font-bold tracking-wide text-white shadow-soft">
                    {listing.discount_percent}% OFF
                  </span>
                )}
                {listing.provider.is_sample && <SampleBadge />}
              </div>
              <span className="badge absolute bottom-4 left-4 bg-black/50 text-[12px] font-medium text-white backdrop-blur-md">
                {photoLabel}
              </span>
            </div>
          </div>

          <div className="lg:sticky lg:top-24 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:self-start">
            <div className="animate-rise space-y-5 [animation-delay:80ms]">
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <DietMark diet={listing.diet} label={meta?.labels.diet[listing.diet]} />
                  <span className="rounded-full bg-sage-100 px-2.5 py-0.5 text-[12px] font-semibold text-ink-600">
                    {meta?.labels.meal_type[listing.meal_type]}
                  </span>
                  {!available && <StatusPill status={listing.availability} />}
                </div>
                <h1 className="mt-3 text-[2rem] leading-tight sm:text-[2.5rem]">{listing.title}</h1>
                <p className="mt-2 flex items-center gap-1.5 text-[14.5px] text-ink-600">
                  <Store className="size-4 text-leaf-600" aria-hidden="true" /> {listing.provider.name} · {listing.provider.area}
                </p>
                <div className="mt-5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-display text-[2.6rem] leading-none font-bold">{formatRupees(listing.price_paise)}</span>
                  <span className="text-lg text-ink-500 line-through">{formatRupees(listing.original_price_paise)}</span>
                  <span className="rounded-full bg-leaf-50 px-2.5 py-0.5 text-[13px] font-semibold text-leaf-800">
                    You save {formatRupees(listing.original_price_paise - listing.price_paise)}
                  </span>
                </div>
              </div>

              <div id="reserve" ref={reserveRef} className="scroll-mt-24">
                <ReservePanel listing={listing} onReserved={() => setReserved(true)} />
              </div>

              <div className="card divide-y divide-line">
                <div className="flex gap-3 p-4">
                  <Clock className="mt-0.5 size-5 shrink-0 text-leaf-600" aria-hidden="true" />
                  <div>
                    <p className="font-semibold">
                      Pickup {formatTime(listing.pickup_start)} – {formatTime(listing.pickup_end)}
                    </p>
                    {available && (
                      <p className="text-[13px] text-ink-500">Reservations close {relativeTime(listing.reservations_close_at, now)}</p>
                    )}
                  </div>
                </div>
                <div className="flex gap-3 p-4">
                  <MapPin className="mt-0.5 size-5 shrink-0 text-leaf-600" aria-hidden="true" />
                  <div>
                    <p className="font-semibold">{listing.provider.name}</p>
                    <p className="text-[14px] text-ink-600">
                      {listing.provider.address_line}, {listing.provider.area}, {listing.provider.city}
                    </p>
                    {listing.pickup_instructions && (
                      <p className="mt-2 rounded-xl bg-sage-50 px-3 py-2 text-[14px] text-ink-700">{listing.pickup_instructions}</p>
                    )}
                  </div>
                </div>
                <div className="flex gap-3 p-4">
                  <BadgeCheck className="mt-0.5 size-5 shrink-0 text-leaf-600" aria-hidden="true" />
                  <p className="text-[14px] text-ink-600">
                    {meta?.labels.fssai_kind[listing.provider.fssai_kind] ?? "FSSAI"} no.{" "}
                    <span className="font-mono font-semibold text-ink-900">{listing.provider.fssai_number}</span>
                  </p>
                </div>
              </div>
            </div>
          </div>

          <section className="lg:col-start-1 lg:row-start-2" aria-labelledby="details-title">
            <h2 id="details-title" className="text-2xl">
              Food details
            </h2>
            {listing.description && <p className="mt-3 text-[15.5px] leading-relaxed text-ink-700">{listing.description}</p>}
            <dl className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
              {[
                { icon: StorageIcon, label: "Stored", value: meta?.labels.storage[listing.storage] ?? listing.storage },
                { icon: Clock, label: "Prepared", value: formatDateTime(listing.prepared_at, now) },
                { icon: Hourglass, label: "Eat by", value: formatDateTime(listing.safe_until, now) },
              ].map((item) => (
                <div key={item.label} className="card flex gap-3 p-4">
                  <item.icon className="mt-0.5 size-5 shrink-0 text-leaf-600" aria-hidden="true" />
                  <div className="min-w-0">
                    <dt className="text-[12.5px] text-ink-500">{item.label}</dt>
                    <dd className="text-[14.5px] font-semibold text-ink-900">{item.value}</dd>
                  </div>
                </div>
              ))}
            </dl>
            <div className="card mt-3 p-5">
              <h3 className="flex items-center gap-2 font-sans text-[15px] font-semibold tracking-normal">
                <Wheat className="size-5 text-leaf-600" aria-hidden="true" /> Allergens
              </h3>
              {listing.allergens.length > 0 ? (
                <ul className="mt-3 flex flex-wrap gap-2">
                  {listing.allergens.map((allergen) => (
                    <li key={allergen} className="badge bg-saffron-50 px-3 py-1 text-[13px] text-saffron-600 ring-1 ring-saffron-100">
                      {meta?.labels.allergen[allergen] ?? allergen}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-[15px] text-ink-600">The kitchen declared none of the listed allergens.</p>
              )}
              {listing.allergen_note && <p className="mt-3 text-sm text-ink-600">Note from the kitchen: {listing.allergen_note}</p>}
              <p className="mt-3 text-[12.5px] text-ink-500">
                Allergen information comes from the kitchen. If you have a severe allergy, check with them before eating.
              </p>
            </div>
          </section>
        </div>
      </div>

      {available && !reserved && !reserveVisible && (
        <div className="fixed inset-x-0 bottom-0 z-30 animate-fade border-t border-line bg-white/95 px-4 py-3 shadow-[0_-10px_30px_-18px_rgb(20_29_24/0.4)] backdrop-blur lg:hidden">
          <div className="mx-auto flex max-w-xl items-center justify-between gap-4">
            <div>
              <p className="font-display text-2xl leading-none font-bold">{formatRupees(listing.price_paise)}</p>
              <p className="mt-0.5 text-[12.5px] text-ink-500">
                Pickup by {formatTime(listing.pickup_end)} · {listing.quantity_available} left
              </p>
            </div>
            <a href="#reserve" className="btn-primary px-6">
              Reserve
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
