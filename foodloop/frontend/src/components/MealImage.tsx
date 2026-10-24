import { useState } from "react";

import type { MealType } from "../api/types";
import { MEAL_ILLUSTRATIONS } from "../lib/meals";
import { photoForMeal } from "../lib/photos";
import { Photo } from "./Photo";

/**
 * A meal's picture. The kitchen's own upload always wins. Without one, a matching food photo is shown and
 * labelled "Representative image" by the caller, so nobody mistakes it for the real batch.
 */
export function MealImage({
  imageUrl,
  mealType,
  title = "",
  seed,
  alt,
  className = "",
  sizes = "(min-width: 1024px) 380px, (min-width: 640px) 50vw, 100vw",
}: {
  imageUrl: string | null;
  mealType: MealType;
  /** The meal's name, used to pick a matching representative photo. */
  title?: string;
  /** Keeps the same representative photo for the same meal across renders. */
  seed?: string;
  alt: string;
  className?: string;
  sizes?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (imageUrl && !failed) {
    return (
      <img
        src={imageUrl}
        alt={alt}
        loading="lazy"
        decoding="async"
        onError={() => setFailed(true)}
        className={`h-full w-full object-cover ${className}`}
      />
    );
  }
  if (imageUrl && failed) {
    return <img src={MEAL_ILLUSTRATIONS[mealType]} alt={alt} className={`h-full w-full object-cover ${className}`} />;
  }
  const representative = photoForMeal(mealType, title, seed ?? title);
  return <Photo photo={representative} sizes={sizes} alt={alt ? `${alt} (representative image)` : ""} className={className} />;
}
