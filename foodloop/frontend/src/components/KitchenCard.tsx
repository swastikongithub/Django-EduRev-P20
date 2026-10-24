import { ArrowRight, MapPin, Utensils } from "lucide-react";
import { Link } from "react-router";

import { useMeta } from "../api/queries";
import type { KitchenCard as Kitchen, Listing } from "../api/types";
import { formatRupees, plural } from "../lib/format";
import { collagePhotos } from "../lib/photos";
import { Photo } from "./Photo";
import { SampleBadge } from "./ui";

/** A kitchen with a collage of the dishes it has on offer right now. */
export function KitchenCard({ kitchen, dishes, className = "" }: { kitchen: Kitchen; dishes: Listing[]; className?: string }) {
  const { data: meta } = useMeta();
  const photos = collagePhotos(dishes);
  return (
    <Link
      to={`/kitchens/${kitchen.slug}`}
      className={`group card flex flex-col overflow-hidden transition duration-300 hover:-translate-y-1 hover:border-leaf-200 hover:shadow-lift ${className}`}
    >
      <div className="relative grid aspect-[16/10] grid-cols-[1.6fr_1fr] grid-rows-2 gap-1 bg-cream-200">
        {photos.map((photo, index) => (
          <div key={`${photo.slug}-${index}`} className={`overflow-hidden ${index === 0 ? "row-span-2" : ""}`}>
            <Photo
              photo={photo}
              alt=""
              sizes={index === 0 ? "240px" : "140px"}
              className="transition duration-700 group-hover:scale-[1.06]"
            />
          </div>
        ))}
        {kitchen.is_sample && <SampleBadge className="absolute top-3 left-3" />}
      </div>
      <div className="flex flex-1 flex-col p-5">
        <p className="text-[12px] font-bold tracking-wide text-leaf-700 uppercase">{meta?.labels.provider_kind[kitchen.kind]}</p>
        <h3 className="mt-1 text-lg leading-snug transition-colors group-hover:text-leaf-700">
          {kitchen.name.replace(/^\[SAMPLE\]\s*/, "")}
        </h3>
        <p className="mt-1 flex items-center gap-1.5 text-[13.5px] text-ink-500">
          <MapPin className="size-3.5" aria-hidden="true" /> {kitchen.area}, {kitchen.city}
        </p>
        {kitchen.description && <p className="mt-2 line-clamp-2 text-[14px] leading-relaxed text-ink-600">{kitchen.description}</p>}
        <div className="mt-auto flex items-center justify-between gap-3 pt-4">
          <span className="inline-flex items-center gap-1.5 text-[13.5px] font-semibold text-ink-900">
            <Utensils className="size-4 text-leaf-600" aria-hidden="true" />
            {kitchen.live_meals > 0 ? plural(kitchen.live_meals, "meal") + " now" : "Nothing listed right now"}
          </span>
          {kitchen.lowest_price_paise !== null && (
            <span className="text-[13.5px] text-ink-600">
              from <strong className="text-leaf-700">{formatRupees(kitchen.lowest_price_paise)}</strong>
            </span>
          )}
        </div>
      </div>
      <span className="flex items-center justify-between border-t border-line/70 px-5 py-3 text-[13.5px] font-semibold text-leaf-700">
        See the kitchen's menu
        <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
      </span>
    </Link>
  );
}
