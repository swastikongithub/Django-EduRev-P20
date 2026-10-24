// Questions people ask, answered by how FoodLoop actually works today. Shared by the FAQ page and the home page.

export interface FaqItem {
  q: string;
  a: string;
}

export const FAQ: { title: string; items: FaqItem[] }[] = [
  {
    title: "For customers",
    items: [
      {
        q: "What is FoodLoop?",
        a: "A way to buy good food that would otherwise go to waste. Approved canteens, cafeterias, hostel messes and PG kitchens list their safe surplus at a lower price. You reserve online, then collect it from the kitchen before the pickup deadline.",
      },
      {
        q: "How do I pay?",
        a: "You pay the kitchen directly at the counter when you collect your meal, by UPI or cash, whichever the kitchen accepts. FoodLoop doesn't take online payments yet.",
      },
      {
        q: "Is the food safe to eat?",
        a: "Only kitchens with a valid FSSAI registration or licence, checked by FoodLoop, can list food. Every meal has a pickup window and an eat-by time based on how it was stored, and the website refuses reservations once the window is closing. Kitchens declare allergens and veg or non-veg status for every listing.",
      },
      {
        q: "What if I can't make it to the pickup?",
        a: "Cancel from My reservations any time before the pickup window ends. The portions go straight back on sale so someone else can enjoy them.",
      },
      {
        q: "How many portions can I reserve?",
        a: "Up to the limit the kitchen sets for each meal, and up to 3 open reservations at a time, so food reaches as many people as possible.",
      },
      {
        q: "Why does a photo say “Representative image”?",
        a: "The kitchen hasn't uploaded a photo of today's batch, so we show a matching food photo instead and label it clearly. The real meal may look different.",
      },
      {
        q: "What does “Sample data” mean?",
        a: "Kitchens and meals marked “Sample data” are made up for demonstrations and testing. They aren't real businesses or real food.",
      },
    ],
  },
  {
    title: "For kitchens",
    items: [
      {
        q: "Who can list food on FoodLoop?",
        a: "College canteens, office cafeterias, hostel messes and PG kitchens with a valid FSSAI registration or licence. FoodLoop checks your details before your listings go live.",
      },
      {
        q: "How do I get paid?",
        a: "Customers pay you directly at your counter, the same way they pay for any meal. FoodLoop never handles the money. Any future platform fee would be agreed with kitchens in advance.",
      },
      {
        q: "How long does listing take?",
        a: "Under a minute: name the dish, set the price and portions, pick a pickup window and confirm the food-safety checklist.",
      },
      {
        q: "How does the handover work?",
        a: "The customer shows a 6-character pickup code. Type it into your dashboard and the meal is marked as collected.",
      },
      {
        q: "What if a customer doesn't turn up?",
        a: "After the pickup window ends the reservation is marked as not collected. Food must never be sold after its eat-by time, on FoodLoop or anywhere else.",
      },
    ],
  },
];
