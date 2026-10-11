import { Clock, MapPin } from "lucide-react";
import { Link } from "react-router";

import { useMeta } from "../api/queries";
import type { Listing } from "../api/types";
import { formatRupees, formatWindow, minutesUntil, relativeTime } from "../lib/format";
import { useNow } from "../lib/useNow";
import { MealImage } from "./MealImage";
import { DietMark, SampleBadge, StatusPill } from "./ui";

export function ListingCard({ listing, index = 0 }: { listing: Listing; index?: number }) {
  const now = useNow();
  const { data: meta } = useMeta();
  const closesIn = minutesUntil(listing.reservations_close_at, now);
  const urgent = listing.availability === "available" && closesIn <= 30;
  const lowStock = listing.availability === "available" && listing.quantity_available <= 3;
  const unavailable = listing.availability !== "available";

  return (
    <Link
      to={`/meals/${listing.id}`}
      className="group card flex animate-rise flex-col overflow-hidden transition duration-300 hover:-translate-y-1 hover:shadow-lift"
      style={{ animationDelay: `${Math.min(index, 8) * 50}ms` }}
    >
      <div className="relative aspect-[4/3] overflow-hidden bg-cream-200">
        <MealImage
          imageUrl={listing.image_url}
          mealType={listing.meal_type}
          alt={listing.title}
          className={`transition duration-500 group-hover:scale-[1.04] ${unavailable ? "opacity-60 grayscale-[40%]" : ""}`}
        />
        <div className="absolute inset-x-3 top-3 flex items-start justify-between gap-2">
          {listing.discount_percent > 0 ? (
            <span className="badge bg-saffron-600 px-3 py-1 text-[13px] text-white shadow-soft">
              {listing.discount_percent}% off
            </span>
          ) : (
            <span />
          )}
          {listing.provider.is_sample && <SampleBadge />}
        </div>
        <div className="absolute bottom-3 left-3 flex gap-1.5">
          {unavailable && <StatusPill status={listing.availability} />}
          {!listing.image_url && (
            <span className="badge bg-white/90 text-[11px] text-ink-600 backdrop-blur">Illustration</span>
          )}
          {listing.image_url && listing.image_is_representative && (
            <span className="badge bg-white/90 text-[11px] text-ink-600 backdrop-blur">Representative photo</span>
          )}
        </div>
      </div>
      <div className="flex flex-1 flex-col p-4 sm:p-5">
        <div className="flex items-center justify-between gap-2">
          <DietMark diet={listing.diet} label={meta?.labels.diet[listing.diet]} />
          <span className="text-[12px] font-semibold tracking-wide text-ink-500 uppercase">
            {meta?.labels.meal_type[listing.meal_type] ?? listing.meal_type}
          </span>
        </div>
        <h3 className="mt-2 line-clamp-2 font-display text-[1.15rem] leading-snug font-semibold text-ink-900 group-hover:text-leaf-700">
          {listing.title}
        </h3>
        <p className="mt-1 flex items-center gap-1 truncate text-[13px] text-ink-500">
          <MapPin className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">
            {listing.provider.name} · {listing.provider.area}
          </span>
        </p>
        <div className="mt-4 flex items-end justify-between gap-3">
          <p className="flex items-baseline gap-2">
            <span className="font-display text-2xl font-semibold text-ink-900">{formatRupees(listing.price_paise)}</span>
            <span className="text-sm text-ink-500 line-through">{formatRupees(listing.original_price_paise)}</span>
          </p>
          {listing.availability === "available" && (
            <span className={`text-[13px] font-semibold ${lowStock ? "text-saffron-600" : "text-leaf-700"}`}>
              {listing.quantity_available} left
            </span>
          )}
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-line/70 pt-3 text-[13px]">
          <span className="flex items-center gap-1.5 text-ink-600">
            <Clock className="size-3.5" aria-hidden="true" />
            Pickup {formatWindow(listing.pickup_start, listing.pickup_end, now)}
          </span>
          {listing.availability === "available" && (
            <span className={urgent ? "font-semibold text-saffron-600" : "text-ink-500"}>
              Closes {relativeTime(listing.reservations_close_at, now)}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

export function ListingCardSkeleton() {
  return (
    <div className="card overflow-hidden" aria-hidden="true">
      <div className="skeleton aspect-[4/3] rounded-none" />
      <div className="space-y-3 p-5">
        <div className="skeleton h-4 w-24" />
        <div className="skeleton h-5 w-4/5" />
        <div className="skeleton h-4 w-3/5" />
        <div className="skeleton mt-4 h-7 w-28" />
      </div>
    </div>
  );
}
