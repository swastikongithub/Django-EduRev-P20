// Food photography catalogue. Files live in public/photos as `${slug}-${width}.webp` (Adobe Stock, see
// docs/image-credits.md). They are not in Git, so every photo has an illustration fallback.

import type { Listing, MealType } from "../api/types";
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
  masalaDosa: photo("masala-dosa", "Masala dosa on a banana leaf with sambar and chutneys", MEAL_ILLUSTRATIONS.breakfast),
  poha: photo("poha", "A bowl of poha with peanuts and coriander", MEAL_ILLUSTRATIONS.breakfast),
  upma: photo("upma", "Vegetable rava upma served on a leaf", MEAL_ILLUSTRATIONS.breakfast),
  alooParatha: photo("aloo-paratha", "Aloo paratha with a bowl of curd", MEAL_ILLUSTRATIONS.breakfast),
  rajmaChawal: photo("rajma-chawal", "Rajma curry with rice, onions and cucumber", MEAL_ILLUSTRATIONS.lunch),
  choleBhature: photo("chole-bhature", "Chole bhature with onions and pickle", MEAL_ILLUSTRATIONS.lunch),
  paneerMasala: photo("paneer-masala", "Paneer butter masala in a black serving dish", MEAL_ILLUSTRATIONS.dinner),
  curdRice: photo("curd-rice", "A bowl of South Indian curd rice", MEAL_ILLUSTRATIONS.lunch),
  dalMakhani: photo("dal-makhani", "Dal makhani with rice and flatbread", MEAL_ILLUSTRATIONS.dinner),
  chickenCurry: photo("chicken-curry", "Chicken curry with naan", MEAL_ILLUSTRATIONS.dinner),
  eggCurry: photo("egg-curry", "Egg curry in a white bowl", MEAL_ILLUSTRATIONS.dinner),
  hakkaNoodles: photo("hakka-noodles", "Vegetable hakka noodles in a bowl", MEAL_ILLUSTRATIONS.snacks),
  momos: photo("momos", "Steamed momos with red chilli chutney", MEAL_ILLUSTRATIONS.snacks),
  vadaPav: photo("vada-pav", "Vada pav with fried green chilli", MEAL_ILLUSTRATIONS.snacks),
  pavBhaji: photo("pav-bhaji", "Pav bhaji with buttered pav and lemon", MEAL_ILLUSTRATIONS.snacks),
  sandwich: photo("sandwich", "A stack of grilled sandwiches", MEAL_ILLUSTRATIONS.snacks),
  gulabJamun: photo("gulab-jamun", "Gulab jamun on a dark plate", MEAL_ILLUSTRATIONS.snacks),
  fruitBowl: photo("fruit-bowl", "A bowl of freshly cut mixed fruit", MEAL_ILLUSTRATIONS.breakfast),
  brownies: photo("brownies", "Chocolate brownies on a white plate", MEAL_ILLUSTRATIONS.bakery),
  filterCoffee: photo("filter-coffee", "South Indian filter coffee on roasted coffee beans", MEAL_ILLUSTRATIONS.beverages),
  coldCoffee: photo("cold-coffee", "A tall glass of iced coffee with milk", MEAL_ILLUSTRATIONS.beverages),
  lassi: photo("lassi", "Sweet lassi topped with nuts in a brass glass", MEAL_ILLUSTRATIONS.beverages),
  limeSoda: photo("lime-soda", "Fresh lime soda with mint and ice", MEAL_ILLUSTRATIONS.beverages),
} satisfies Record<string, Photo>;

export function photoSrc(item: Photo, width = item.widths[1] ?? item.widths[0]): string {
  return `/photos/${item.slug}-${width}.webp`;
}

export function photoSrcSet(item: Photo): string {
  return item.widths.map((width) => `/photos/${item.slug}-${width}.webp ${width}w`).join(", ");
}

const BY_MEAL: Record<MealType, Photo[]> = {
  breakfast: [PHOTOS.idliVada, PHOTOS.masalaDosa, PHOTOS.poha, PHOTOS.alooParatha],
  lunch: [PHOTOS.steelThali, PHOTOS.lunchTray, PHOTOS.rajmaChawal, PHOTOS.choleBhature],
  snacks: [PHOTOS.samosa, PHOTOS.vadaPav, PHOTOS.momos, PHOTOS.pavBhaji],
  dinner: [PHOTOS.biryaniPan, PHOTOS.dalMakhani, PHOTOS.chickenCurry, PHOTOS.paneerMasala],
  bakery: [PHOTOS.croissants, PHOTOS.breadBuns, PHOTOS.brownies],
  beverages: [PHOTOS.masalaChai, PHOTOS.chaiPour, PHOTOS.coldCoffee, PHOTOS.lassi],
};

// The meal's name says more than its category: "Chicken biryani" listed under lunch should look like biryani.
// Order matters: the first match wins, so specific dishes come before general words.
const KEYWORDS: [RegExp, Photo][] = [
  [/vada ?pav|wada ?pav/i, PHOTOS.vadaPav],
  [/pav ?bhaji/i, PHOTOS.pavBhaji],
  [/dosa|uttapam/i, PHOTOS.masalaDosa],
  [/idli|idly|vada|sambar/i, PHOTOS.idliVada],
  [/poha/i, PHOTOS.poha],
  [/upma/i, PHOTOS.upma],
  [/paratha/i, PHOTOS.alooParatha],
  [/sandwich|toast/i, PHOTOS.sandwich],
  [/chicken biryani|mutton biryani/i, PHOTOS.biryaniBowl],
  [/biryani|pulao/i, PHOTOS.biryaniPan],
  [/chole|chana|bhature/i, PHOTOS.choleBhature],
  [/rajma/i, PHOTOS.rajmaChawal],
  [/curd rice|dahi chawal/i, PHOTOS.curdRice],
  [/dal makhani|dinner thali/i, PHOTOS.dalMakhani],
  [/paneer|butter masala|shahi/i, PHOTOS.paneerMasala],
  [/egg curry|anda|egg masala/i, PHOTOS.eggCurry],
  [/chicken|mutton|murg/i, PHOTOS.chickenCurry],
  [/thali|dal|curry rice|meals?\b/i, PHOTOS.steelThali],
  [/momo/i, PHOTOS.momos],
  [/noodle|chow ?mein|hakka/i, PHOTOS.hakkaNoodles],
  [/samosa|pakora|kachori|bhaji/i, PHOTOS.samosa],
  [/wrap|roll|frankie|kathi/i, PHOTOS.vegWrap],
  [/fruit/i, PHOTOS.fruitBowl],
  [/salad|sprout/i, PHOTOS.saladBowl],
  [/gulab|jamun|rasgulla|halwa|kheer/i, PHOTOS.gulabJamun],
  [/cold coffee|iced coffee/i, PHOTOS.coldCoffee],
  [/coffee/i, PHOTOS.filterCoffee],
  [/lassi|chaas|buttermilk/i, PHOTOS.lassi],
  [/lime|lemon|nimbu|soda/i, PHOTOS.limeSoda],
  [/chai|tea\b/i, PHOTOS.masalaChai],
  [/bun|bread|loaf/i, PHOTOS.breadBuns],
  [/brownie|cake|chocolate/i, PHOTOS.brownies],
  [/croissant|pastry|puff|muffin|cookie/i, PHOTOS.croissants],
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
  { mealType: "breakfast", label: "Breakfast", photo: PHOTOS.masalaDosa },
  { mealType: "lunch", label: "Lunch", photo: PHOTOS.steelThali },
  { mealType: "snacks", label: "Snacks", photo: PHOTOS.samosa },
  { mealType: "dinner", label: "Dinner", photo: PHOTOS.biryaniPan },
  { mealType: "bakery", label: "Bakery", photo: PHOTOS.croissants },
  { mealType: "beverages", label: "Drinks", photo: PHOTOS.masalaChai },
];

/** Three different photos for a kitchen's collage: its own dishes first, then kitchen scenes. */
export function collagePhotos(dishes: Listing[]): Photo[] {
  const picked: Photo[] = [];
  for (const dish of dishes) {
    const photo = photoForMeal(dish.meal_type, dish.title, dish.id);
    if (!picked.includes(photo)) picked.push(photo);
    if (picked.length === 3) return picked;
  }
  for (const photo of [PHOTOS.canteenServing, PHOTOS.chefKitchen, PHOTOS.steelThali]) {
    if (picked.length < 3 && !picked.includes(photo)) picked.push(photo);
  }
  return picked;
}
