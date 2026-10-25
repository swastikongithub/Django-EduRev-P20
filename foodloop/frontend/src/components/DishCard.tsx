import { Plus } from "lucide-react";
import { Link } from "react-router";

import type { Listing } from "../api/types";
import { formatRupees } from "../lib/format";
import { Countdown } from "./Live";
import { MealImage } from "./MealImage";
import { DietMark, SampleBadge } from "./ui";

/** A compact dish card: a round "plate" photo rising out of the card, name, kitchen, price and a reserve button. */
export function DishCard({ listing }: { listing: Listing }) {
  return (
    <Link
      to={`/meals/${listing.id}`}
      className="group relative mt-14 flex flex-col items-center rounded-[1.75rem] border border-line bg-panel px-4 pb-4 text-center shadow-soft transition duration-300 hover:-translate-y-1 hover:border-brand-500/60 hover:shadow-lift sm:px-5 sm:pb-5"
    >
      <span
        className="plate -mt-14 block size-28 bg-raised transition duration-500 group-hover:rotate-6 sm:size-32"
        title={listing.image_url ? undefined : "Representative image"}
      >
        <MealImage
          imageUrl={listing.image_url}
          mealType={listing.meal_type}
          title={listing.title}
          seed={listing.id}
          alt=""
          sizes="128px"
          className="scale-110"
        />
      </span>
      <span className="mt-3 flex items-center gap-2">
        <DietMark diet={listing.diet} />
        {listing.provider.is_sample && <SampleBadge className="!text-[9.5px]" />}
      </span>
      <span className="mt-2 line-clamp-2 min-h-[2.6em] text-[15px] leading-snug font-semibold text-fg transition-colors group-hover:text-brand-400">
        {listing.title}
      </span>
      <span className="mt-1 w-full truncate text-[12.5px] text-fg-muted">{listing.provider.name.replace(/^\[SAMPLE\]\s*/, "")}</span>
      <Countdown to={listing.reservations_close_at} className="mt-1.5 text-[12px]" />
      <span className="mt-4 flex w-full items-center justify-between gap-2">
        <span className="text-left">
          <span className="font-display block text-xl leading-none font-bold text-brand-400">{formatRupees(listing.price_paise)}</span>
          <span className="text-[12px] text-fg-muted">
            <span className="line-through">{formatRupees(listing.original_price_paise)}</span>
            {listing.discount_percent > 0 && <span className="ml-1.5 font-semibold text-brand-300">−{listing.discount_percent}%</span>}
          </span>
        </span>
        <span
          className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-500 text-night shadow-glow transition group-hover:scale-110 group-hover:bg-brand-400"
          aria-hidden="true"
        >
          <Plus className="size-5" strokeWidth={2.6} />
        </span>
      </span>
      <span className="sr-only">Reserve</span>
    </Link>
  );
}
