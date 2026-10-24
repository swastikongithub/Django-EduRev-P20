import { Link } from "react-router";

import { useMeta } from "../api/queries";
import type { Listing } from "../api/types";
import { formatRupees } from "../lib/format";
import { Countdown } from "./Live";
import { MealImage } from "./MealImage";
import { DietMark, SampleBadge } from "./ui";

/** One dish in a restaurant-style menu: photo, name, kitchen, price and how long it can still be reserved. */
export function MenuRow({ listing, showKitchen = true }: { listing: Listing; showKitchen?: boolean }) {
  const { data: meta } = useMeta();
  return (
    <Link
      to={`/meals/${listing.id}`}
      className="group flex min-w-0 items-center gap-4 rounded-2xl p-2.5 transition hover:bg-white hover:shadow-soft"
    >
      <span className="relative size-16 shrink-0 overflow-hidden rounded-2xl bg-cream-200 sm:size-[4.5rem]">
        <MealImage
          imageUrl={listing.image_url}
          mealType={listing.meal_type}
          title={listing.title}
          seed={listing.id}
          alt=""
          sizes="72px"
          className="transition duration-500 group-hover:scale-110"
        />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <DietMark diet={listing.diet} />
          <span className="truncate text-[15px] font-semibold text-ink-900 group-hover:text-leaf-700">{listing.title}</span>
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[12.5px] text-ink-500">
          {showKitchen && <span className="truncate">{listing.provider.name.replace(/^\[SAMPLE\]\s*/, "")}</span>}
          <Countdown to={listing.reservations_close_at} className="text-[12px]" />
          {listing.provider.is_sample && <SampleBadge className="!text-[9.5px]" />}
        </span>
        <span className="sr-only">{meta?.labels.meal_type[listing.meal_type]}</span>
      </span>
      <span className="shrink-0 text-right">
        <span className="font-display block text-xl leading-none font-bold text-ink-900">{formatRupees(listing.price_paise)}</span>
        <span className="mt-1 block text-[12px] text-ink-500">
          <span className="line-through">{formatRupees(listing.original_price_paise)}</span>
          {listing.discount_percent > 0 && <span className="ml-1.5 font-semibold text-saffron-600">−{listing.discount_percent}%</span>}
        </span>
      </span>
    </Link>
  );
}
