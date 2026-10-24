// Food photography catalogue. Files live in public/photos as `${slug}-${width}.webp` (Adobe Stock, see
// docs/image-credits.md). They are not in Git, so every photo has an illustration fallback.

import type { MealType } from "../api/types";
import { MEAL_ILLUSTRATIONS } from "./meals";

export interface Photo {
  slug: string;
  alt: string;
  widths: number[];
  /** Shown if the photo is missing or fails to load. */
  fallback: string;
}

const CARD_WIDTHS = [480, 800, 1200];

function photo(slug: string, alt: string, fallback: string, widths = CARD_WIDTHS): Photo {
  return { slug, alt, widths, fallback };
}

export const PHOTOS = {
  thaliSpread: photo(
    "thali-spread",
    "A spread of Indian vegetarian dishes in steel bowls: dal, paneer curry, rice, rotis and sweets",
    MEAL_ILLUSTRATIONS.lunch,
    [640, 1024, 1600],
  ),
  steelThali: photo("steel-thali", "A vegetarian thali with dal, sabzi, rice and roti on a steel plate", MEAL_ILLUSTRATIONS.lunch),
  lunchTray: photo("lunch-tray", "A mini meal tray with curries, rice, roti and sides", MEAL_ILLUSTRATIONS.lunch),
  biryaniPan: photo("biryani-pan", "Fragrant biryani served in a black pan", MEAL_ILLUSTRATIONS.dinner),
  biryaniBowl: photo("biryani-bowl", "Chicken biryani in a brass bowl", MEAL_ILLUSTRATIONS.dinner),
  idliVada: photo("idli-vada", "Idli and vada with sambar and coconut chutney", MEAL_ILLUSTRATIONS.breakfast),
  idliTop: photo("idli-top", "Soft idlis with chutney and sambar, seen from above", MEAL_ILLUSTRATIONS.breakfast),
  samosa: photo("samosa", "Crispy Punjabi samosas with green chutney", MEAL_ILLUSTRATIONS.snacks),
  vegWrap: photo("veg-wrap", "A fresh vegetable wrap cut in half", MEAL_ILLUSTRATIONS.snacks),
  croissants: photo("croissants", "Freshly baked croissants and pastries", MEAL_ILLUSTRATIONS.bakery),
  breadBuns: photo("bread-buns", "Rows of freshly baked bread buns", MEAL_ILLUSTRATIONS.bakery),
  masalaChai: photo("masala-chai", "A glass cup of masala chai with cinnamon and star anise", MEAL_ILLUSTRATIONS.beverages),
  chaiPour: photo("chai-pour", "Hot chai being poured into glass cups", MEAL_ILLUSTRATIONS.beverages),
  saladBowl: photo("salad-bowl", "A bowl of fresh vegetable salad held in two hands", MEAL_ILLUSTRATIONS.lunch),
  canteenServing: photo("canteen-serving", "A canteen worker serving food from a buffet counter", MEAL_ILLUSTRATIONS.lunch),
  chefKitchen: photo("chef-kitchen", "Chefs cooking in a busy commercial kitchen", MEAL_ILLUSTRATIONS.dinner),
  takeawayBag: photo("takeaway-bag", "Takeaway food boxes next to a paper carry bag", MEAL_ILLUSTRATIONS.lunch),
  foodWaste: photo("food-waste", "Food scraps being scraped into a kitchen bin", MEAL_ILLUSTRATIONS.lunch, [480, 800]),
} satisfies Record<string, Photo>;

export function photoSrc(item: Photo, width = item.widths[1] ?? item.widths[0]): string {
  return `/photos/${item.slug}-${width}.webp`;
}

export function photoSrcSet(item: Photo): string {
  return item.widths.map((width) => `/photos/${item.slug}-${width}.webp ${width}w`).join(", ");
}

const BY_MEAL: Record<MealType, Photo[]> = {
  breakfast: [PHOTOS.idliVada, PHOTOS.idliTop],
  lunch: [PHOTOS.steelThali, PHOTOS.lunchTray],
  snacks: [PHOTOS.samosa, PHOTOS.vegWrap],
  dinner: [PHOTOS.biryaniPan, PHOTOS.biryaniBowl],
  bakery: [PHOTOS.croissants, PHOTOS.breadBuns],
  beverages: [PHOTOS.masalaChai, PHOTOS.chaiPour],
};

// The meal's name says more than its category: "Chicken biryani" listed under lunch should look like biryani.
const KEYWORDS: [RegExp, Photo][] = [
  [/biryani|pulao|fried rice/i, PHOTOS.biryaniPan],
  [/thali|dal|rajma|chawal|curry rice|meals?\b/i, PHOTOS.steelThali],
  [/idli|idly|vada|dosa|uttapam|upma|sambar/i, PHOTOS.idliVada],
  [/samosa|pakora|kachori|bhaji/i, PHOTOS.samosa],
  [/wrap|roll|frankie|sandwich|kathi/i, PHOTOS.vegWrap],
  [/salad|sprout/i, PHOTOS.saladBowl],
  [/chai|tea|coffee|lassi|juice/i, PHOTOS.masalaChai],
  [/croissant|pastry|puff|cake|muffin|cookie/i, PHOTOS.croissants],
  [/bun|bread|pav|loaf/i, PHOTOS.breadBuns],
];

function stableIndex(seed: string, length: number): number {
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash % length;
}

/** A representative photo for a meal without its own photo: matched by name, else by meal type. */
export function photoForMeal(mealType: MealType, title = "", seed = title): Photo {
  for (const [pattern, match] of KEYWORDS) {
    if (pattern.test(title)) return match;
  }
  const options = BY_MEAL[mealType];
  return options[stableIndex(seed, options.length)];
}

export const CATEGORY_PHOTOS: { mealType: MealType; label: string; photo: Photo }[] = [
  { mealType: "breakfast", label: "Breakfast", photo: PHOTOS.idliVada },
  { mealType: "lunch", label: "Lunch", photo: PHOTOS.steelThali },
  { mealType: "snacks", label: "Snacks", photo: PHOTOS.samosa },
  { mealType: "dinner", label: "Dinner", photo: PHOTOS.biryaniPan },
  { mealType: "bakery", label: "Bakery", photo: PHOTOS.croissants },
  { mealType: "beverages", label: "Drinks", photo: PHOTOS.masalaChai },
];
