import bakery from "../assets/meals/bakery.svg";
import beverages from "../assets/meals/beverages.svg";
import breakfast from "../assets/meals/breakfast.svg";
import dinner from "../assets/meals/dinner.svg";
import lunch from "../assets/meals/lunch.svg";
import snacks from "../assets/meals/snacks.svg";
import type { MealType } from "../api/types";

// Shown when a kitchen hasn't uploaded a photo. Clearly an illustration, never mistaken for the real food.
export const MEAL_ILLUSTRATIONS: Record<MealType, string> = { breakfast, lunch, snacks, dinner, bakery, beverages };

export const ALLERGEN_KEYS = [
  "gluten",
  "milk",
  "egg",
  "peanut",
  "tree_nut",
  "soy",
  "fish",
  "crustacean",
  "sesame",
  "mustard",
  "sulphite",
] as const;
