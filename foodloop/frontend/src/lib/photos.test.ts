import { describe, expect, it } from "vitest";

import { PHOTOS, photoForMeal } from "./photos";

describe("photoForMeal", () => {
  it("matches the dish by name before falling back to its meal type", () => {
    expect(photoForMeal("snacks", "Vada pav (2 pcs)")).toBe(PHOTOS.vadaPav);
    expect(photoForMeal("snacks", "Pav bhaji")).toBe(PHOTOS.pavBhaji);
    expect(photoForMeal("breakfast", "Medu vada (2 pcs) with sambar")).toBe(PHOTOS.idliVada);
    expect(photoForMeal("breakfast", "Masala dosa with chutney")).toBe(PHOTOS.masalaDosa);
    expect(photoForMeal("dinner", "Chicken biryani with raita")).toBe(PHOTOS.biryaniBowl);
    expect(photoForMeal("dinner", "Veg biryani with raita")).toBe(PHOTOS.biryaniPan);
    expect(photoForMeal("dinner", "Chicken curry with 2 rotis")).toBe(PHOTOS.chickenCurry);
    expect(photoForMeal("snacks", "Paneer tikka sandwich")).toBe(PHOTOS.sandwich);
    expect(photoForMeal("snacks", "Bread pakora (2 pcs)")).toBe(PHOTOS.samosa);
    expect(photoForMeal("beverages", "Cold coffee")).toBe(PHOTOS.coldCoffee);
    expect(photoForMeal("beverages", "Filter coffee")).toBe(PHOTOS.filterCoffee);
    expect(photoForMeal("bakery", "Assorted buns and cake slices")).toBe(PHOTOS.breadBuns);
  });

  it("uses a stable photo for the meal type when the name doesn't help", () => {
    const first = photoForMeal("lunch", "Chef's special", "listing-1");
    expect(photoForMeal("lunch", "Chef's special", "listing-1")).toBe(first);
  });
});
