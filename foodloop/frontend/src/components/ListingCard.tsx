import { ArrowRight, Clock, Flame, Store } from "lucide-react";
import { Link } from "react-router";

import { useMeta } from "../api/queries";
import type { Listing } from "../api/types";
import { formatRupees, formatTime, minutesUntil } from "../lib/format";
import { useNow } from "../lib/useNow";
import { Countdown } from "./Live";
import { MealImage } from "./MealImage";
import { DietMark, SampleBadge, StatusPill } from "./ui";

export function ListingCard({ listing, index = 0 }: { listing: Listing; index?: number }) {
  const now = useNow();
  const { data: meta } = useMeta();
  const available = listing.availability === "available";
  const closesIn = minutesUntil(listing.reservations_close_at, now);
  const urgent = available && closesIn <= 30;
  const lowStock = available && listing.quantity_available <= 3;
  const stockPercent = Math.max(6, Math.round((100 * listing.quantity_available) / listing.quantity_total));
  const saving = listing.original_price_paise - listing.price_paise;
  const hasOwnPhoto = Boolean(listing.image_url);

  return (
    <Link
      to={`/meals/${listing.id}`}
      aria-label={`${listing.title} from ${listing.provider.name}. ${formatRupees(listing.price_paise)} instead of ${formatRupees(
        listing.original_price_paise,
      )}. Pickup ${formatTime(listing.pickup_start)} to ${formatTime(listing.pickup_end)}.${
        available ? ` ${listing.quantity_available} left.` : ""
      }${listing.provider.is_sample ? " Sample data." : ""}`}
      className="group card flex animate-rise flex-col overflow-hidden transition duration-300 hover:-translate-y-1 hover:border-brand-700 hover:shadow-lift"
      style={{ animationDelay: `${Math.min(index, 8) * 60}ms` }}
    >
      <div className="relative aspect-[4/3] overflow-hidden bg-raised">
        <MealImage
          imageUrl={listing.image_url}
          mealType={listing.meal_type}
          title={listing.title}
          seed={listing.id}
          alt={listing.title}
          className={`transition duration-700 ease-out group-hover:scale-[1.05] ${available ? "" : "opacity-60 grayscale-[45%]"}`}
        />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/35 to-transparent" />
        <div className="absolute inset-x-3 top-3 flex items-start justify-between gap-2">
          <span className="flex flex-wrap gap-1.5">
            {listing.discount_percent > 0 && (
              <span className="badge bg-brand-600 px-2.5 py-1 text-[12px] font-bold tracking-wide text-night shadow-soft">
                {listing.discount_percent}% OFF
              </span>
            )}
            {urgent && (
              <span className="badge bg-panel/95 px-2.5 py-1 text-[11.5px] font-bold text-brand-400 shadow-soft">
                <Flame className="size-3.5" aria-hidden="true" /> Closing soon
              </span>
            )}
          </span>
          {listing.provider.is_sample && <SampleBadge />}
        </div>
        <div className="absolute bottom-3 left-3 flex flex-wrap gap-1.5">
          {!available && <StatusPill status={listing.availability} />}
          {(!hasOwnPhoto || listing.image_is_representative) && (
            <span className="badge bg-black/45 text-[11px] font-medium text-white backdrop-blur-md">Representative image</span>
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col p-4 sm:p-5">
        <div className="flex items-center justify-between gap-2">
          <DietMark diet={listing.diet} label={meta?.labels.diet[listing.diet]} />
          <span className="rounded-full bg-raised px-2.5 py-0.5 text-[11.5px] font-semibold text-fg-soft">
            {meta?.labels.meal_type[listing.meal_type] ?? listing.meal_type}
          </span>
        </div>
        <h3 className="mt-2.5 line-clamp-2 text-[1.12rem] leading-snug font-semibold text-fg transition-colors group-hover:text-brand-400">
          {listing.title}
        </h3>
        <p className="mt-1 flex items-center gap-1.5 truncate text-[13px] text-fg-muted">
          <Store className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="truncate">
            {listing.provider.name} · {listing.provider.area}
          </span>
        </p>

        <div className="mt-4 flex items-end justify-between gap-3">
          <div>
            <p className="flex items-baseline gap-2">
              <span className="font-display text-[1.65rem] leading-none font-bold text-fg">
                {formatRupees(listing.price_paise)}
              </span>
              <span className="text-sm text-fg-muted line-through">{formatRupees(listing.original_price_paise)}</span>
            </p>
            {saving > 0 && <p className="mt-1 text-[12.5px] font-semibold text-brand-400">You save {formatRupees(saving)}</p>}
          </div>
          {available && (
            <div className="w-24 text-right">
              <p className={`text-[12.5px] font-semibold ${lowStock ? "text-danger-300" : "text-fg-soft"}`}>
                {lowStock ? `Only ${listing.quantity_available} left` : `${listing.quantity_available} of ${listing.quantity_total} left`}
              </p>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-raised" aria-hidden="true">
                <div
                  className={`h-full rounded-full ${lowStock ? "bg-danger-400" : "bg-brand-500"}`}
                  style={{ width: `${stockPercent}%` }}
                />
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center justify-between gap-3 border-t border-line/70 pt-3.5">
          <div className="min-w-0 text-[12.5px] leading-tight">
            <p className="flex items-center gap-1.5 font-semibold text-fg-soft">
              <Clock className="size-3.5 shrink-0 text-brand-400" aria-hidden="true" />
              Pickup {formatTime(listing.pickup_start)} – {formatTime(listing.pickup_end)}
            </p>
            {available &&
              (closesIn <= 180 ? (
                <Countdown to={listing.reservations_close_at} className="mt-0.5 pl-0.5 text-[12.5px]" />
              ) : (
                <p className="mt-0.5 pl-5 text-fg-muted">Reserve until {formatTime(listing.reservations_close_at)}</p>
              ))}
          </div>
          <span
            className={`inline-flex shrink-0 items-center gap-1 rounded-full px-3.5 py-2 text-[13px] font-semibold transition ${
              available
                ? "bg-brand-950 text-brand-300 group-hover:bg-brand-500 group-hover:text-night"
                : "bg-raised text-fg-soft"
            }`}
          >
            {available ? "Reserve" : "View"}
            <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
          </span>
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
        <div className="flex justify-between">
          <div className="skeleton h-4 w-16" />
          <div className="skeleton h-4 w-14" />
        </div>
        <div className="skeleton h-5 w-4/5" />
        <div className="skeleton h-4 w-3/5" />
        <div className="flex justify-between pt-2">
          <div className="skeleton h-8 w-24" />
          <div className="skeleton h-6 w-20" />
        </div>
        <div className="skeleton mt-2 h-9 w-full" />
      </div>
    </div>
  );
}
