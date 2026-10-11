import type { MealType } from "../api/types";
import { MEAL_ILLUSTRATIONS } from "../lib/meals";

export function MealImage({
  imageUrl,
  mealType,
  alt,
  className = "",
}: {
  imageUrl: string | null;
  mealType: MealType;
  alt: string;
  className?: string;
}) {
  return (
    <img
      src={imageUrl ?? MEAL_ILLUSTRATIONS[mealType]}
      alt={imageUrl ? alt : ""}
      loading="lazy"
      decoding="async"
      className={`h-full w-full object-cover ${className}`}
    />
  );
}
