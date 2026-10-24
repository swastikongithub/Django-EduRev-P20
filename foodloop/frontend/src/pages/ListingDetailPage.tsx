import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BadgeCheck,
  CircleCheck,
  Clock,
  Flame,
  Hourglass,
  MapPin,
  Minus,
  Package,
  Plus,
  Snowflake,
  Thermometer,
  Ticket,
  Wheat,
} from "lucide-react";
import { useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { api, ApiError, errorMessage } from "../api/client";
import { keys, useListing, useMe, useMeta } from "../api/queries";
import type { CustomerReservation, Listing, Storage } from "../api/types";
import { MealImage } from "../components/MealImage";
import { DietMark, ErrorState, Notice, PageLoader, SampleBadge, StatusPill } from "../components/ui";
import { formatDateTime, formatRupees, formatTime, formatWindow, relativeTime } from "../lib/format";
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

function ReservePanel({ listing }: { listing: Listing }) {
  const { data: me } = useMe();
  const location = useLocation();
  const queryClient = useQueryClient();
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
        <div className="bg-leaf-600 px-5 py-4 text-white">
          <p className="flex items-center gap-2 font-semibold">
            <CircleCheck className="size-5" aria-hidden="true" /> Reserved! Here's your pickup code
          </p>
        </div>
        <div className="p-5">
          <p className="rounded-2xl border-2 border-dashed border-leaf-200 bg-leaf-50 py-4 text-center font-mono text-3xl font-bold tracking-[0.3em] text-leaf-800">
            {reservation.pickup_code}
          </p>
          <p className="mt-4 text-[15px] text-ink-700">
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
    return <Notice tone="warning" title="Not available to reserve">{UNAVAILABLE_TEXT[listing.availability]}</Notice>;
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-4">
        <span id="qty-label" className="text-sm font-semibold">
          Quantity
        </span>
        <div className="inline-flex items-center gap-1 rounded-full border border-line bg-cream-50 p-1" role="group" aria-labelledby="qty-label">
          <button
            type="button"
            className="grid size-9 place-items-center rounded-full bg-white shadow-soft disabled:opacity-40"
            onClick={() => setQuantity((value) => Math.max(1, value - 1))}
            disabled={quantity <= 1}
            aria-label="One fewer"
          >
            <Minus className="size-4" />
          </button>
          <output className="w-9 text-center font-semibold tabular-nums" aria-live="polite">
            {quantity}
          </output>
          <button
            type="button"
            className="grid size-9 place-items-center rounded-full bg-white shadow-soft disabled:opacity-40"
            onClick={() => setQuantity((value) => Math.min(maxQuantity, value + 1))}
            disabled={quantity >= maxQuantity}
            aria-label="One more"
          >
            <Plus className="size-4" />
          </button>
        </div>
      </div>
      <p className="mt-2 text-[13px] text-ink-500">Up to {listing.max_per_order} per order · {listing.quantity_available} left</p>
      <div className="mt-4 flex items-baseline justify-between border-t border-line pt-4">
        <span className="text-sm text-ink-600">Pay at pickup</span>
        <span className="font-display text-2xl font-semibold">{formatRupees(listing.price_paise * quantity)}</span>
      </div>

      {reserve.isError && (
        <Notice tone="danger" className="mt-4">
          {errorMessage(reserve.error)}
        </Notice>
      )}

      {!me ? (
        <Link to={`/login?next=${encodeURIComponent(location.pathname)}`} className="btn-primary mt-4 w-full">
          Log in to reserve
        </Link>
      ) : me.user.role !== "customer" ? (
        <Notice tone="info" className="mt-4">
          Reservations are made from customer accounts.
        </Notice>
      ) : (
        <button type="button" className="btn-primary mt-4 w-full" disabled={reserve.isPending} onClick={() => reserve.mutate()}>
          {reserve.isPending ? "Reserving…" : `Reserve ${quantity} for ${formatRupees(listing.price_paise * quantity)}`}
        </button>
      )}
      <p className="mt-3 text-center text-[12.5px] text-ink-500">
        Free to cancel until the pickup window ends. Please cancel if your plans change, so someone else can have it.
      </p>
    </div>
  );
}

export function ListingDetailPage() {
  const { id = "" } = useParams();
  const { data: listing, isLoading, isError, error, refetch } = useListing(id);
  const { data: meta } = useMeta();
  const now = useNow();

  if (isLoading) return <PageLoader />;
  if (isError || !listing) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <ErrorState error={error} onRetry={() => refetch()} />
        <div className="text-center">
          <Link to="/meals" className="btn-ghost">
            <ArrowLeft className="size-4" aria-hidden="true" /> Back to meals
          </Link>
        </div>
      </div>
    );
  }

  const StorageIcon = STORAGE_ICONS[listing.storage];
  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">
      <Link to="/meals" className="btn-ghost btn-sm -ml-3">
        <ArrowLeft className="size-4" aria-hidden="true" /> All meals
      </Link>
      <div className="mt-4 grid gap-8 lg:grid-cols-[1.15fr_1fr] lg:gap-12">
        <div className="animate-rise">
          <div className="relative aspect-[4/3] overflow-hidden rounded-[1.75rem] bg-cream-200 shadow-soft">
            <MealImage imageUrl={listing.image_url} mealType={listing.meal_type} title={listing.title} seed={listing.id} alt={listing.title} sizes="(min-width: 1024px) 640px, 100vw" />
            <div className="absolute top-4 left-4 flex gap-2">
              {listing.discount_percent > 0 && (
                <span className="badge bg-saffron-600 px-3 py-1 text-sm text-white">{listing.discount_percent}% off</span>
              )}
              {listing.provider.is_sample && <SampleBadge />}
            </div>
            <span className="badge absolute right-4 bottom-4 bg-white/90 text-xs text-ink-600 backdrop-blur">
              {!listing.image_url ? "Representative image, not the actual food" : listing.image_is_representative ? "Representative photo" : "Photo from the kitchen"}
            </span>
          </div>

          <section className="mt-8">
            <h2 className="text-xl font-semibold">Food details</h2>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="card flex gap-3 p-4">
                <StorageIcon className="mt-0.5 size-5 text-leaf-600" aria-hidden="true" />
                <div>
                  <dt className="text-[13px] text-ink-500">Stored</dt>
                  <dd className="font-semibold">{meta?.labels.storage[listing.storage]}</dd>
                </div>
              </div>
              <div className="card flex gap-3 p-4">
                <Clock className="mt-0.5 size-5 text-leaf-600" aria-hidden="true" />
                <div>
                  <dt className="text-[13px] text-ink-500">Prepared</dt>
                  <dd className="font-semibold">{formatDateTime(listing.prepared_at, now)}</dd>
                </div>
              </div>
            </dl>
            <div className="card mt-3 p-4">
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

        <div className="animate-rise space-y-5 [animation-delay:80ms]">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <DietMark diet={listing.diet} label={meta?.labels.diet[listing.diet]} />
              <span className="text-[12px] font-semibold tracking-wide text-ink-500 uppercase">
                {meta?.labels.meal_type[listing.meal_type]}
              </span>
              {listing.availability !== "available" && <StatusPill status={listing.availability} />}
            </div>
            <h1 className="mt-3 text-3xl leading-tight font-semibold sm:text-4xl">{listing.title}</h1>
            {listing.description && <p className="mt-3 text-[15px] leading-relaxed text-ink-600">{listing.description}</p>}
            <p className="mt-4 flex items-baseline gap-3">
              <span className="font-display text-4xl font-semibold">{formatRupees(listing.price_paise)}</span>
              <span className="text-lg text-ink-500 line-through">{formatRupees(listing.original_price_paise)}</span>
              <span className="text-sm font-semibold text-saffron-600">
                You save {formatRupees(listing.original_price_paise - listing.price_paise)}
              </span>
            </p>
          </div>

          <ReservePanel listing={listing} />

          <div className="card divide-y divide-line">
            <div className="flex gap-3 p-4">
              <Clock className="mt-0.5 size-5 shrink-0 text-leaf-600" aria-hidden="true" />
              <div>
                <p className="font-semibold">Pickup {formatWindow(listing.pickup_start, listing.pickup_end, now)}</p>
                {listing.availability === "available" && (
                  <p className="text-[13px] text-ink-500">Reservations close {relativeTime(listing.reservations_close_at, now)}</p>
                )}
              </div>
            </div>
            <div className="flex gap-3 p-4">
              <Hourglass className="mt-0.5 size-5 shrink-0 text-saffron-600" aria-hidden="true" />
              <div>
                <p className="font-semibold">Eat by {formatDateTime(listing.safe_until, now)}</p>
                <p className="text-[13px] text-ink-500">Please eat it soon after pickup. Don't store it for later.</p>
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
                  <p className="mt-2 rounded-xl bg-cream-100 px-3 py-2 text-[14px] text-ink-700">{listing.pickup_instructions}</p>
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
    </div>
  );
}
