# Food safety and compliance

> **Not legal advice.** This is a working checklist for a student-built pilot. Before charging money or
> launching publicly, confirm the current rules on [fssai.gov.in](https://www.fssai.gov.in) /
> [FoSCoS](https://foscos.fssai.gov.in), or with a food-safety consultant. Rules change, and some sources
> below describe draft text.

## FoodLoop's own safety rules, and where the code enforces them

| Rule | Enforced in |
|---|---|
| A kitchen can't list anything until an admin approves it | `providers.status` defaults to `pending`. `require_approved_provider` in `app/api/deps.py` |
| An expired FSSAI registration stops all sales | registration refuses expired dates. `fssai_valid_until >= today` in the reservation statement. Admins can't approve an expired one |
| Expired food can never be reserved | the reservation statement checks `pickup_end` and `safe_until` against the current time |
| Reservations close before the pickup window ends | `RESERVATION_CUTOFF_MINUTES` (default 10) |
| Food must be eaten within a safe window that depends on how it was stored | `validate_listing()` in `app/services/listings.py`, configurable per storage type |
| Allergens must be declared for every batch | the API requires the `allergens` field (no default). The form requires ticking allergens or “None of these”. A cross-contamination note is available |
| The kitchen confirms a safety checklist on every save | `safety_confirmed` is required. `safety_declared_by` / `safety_declared_at` are recorded |
| Kitchens can't hand over food after its eat-by time | `collect()` refuses after `safe_until` |
| A suspended kitchen's open reservations are cancelled | `providers.suspend()` |
| Pictures are never passed off as the real food | illustrations are labelled. Kitchens can mark a photo as “representative” |
| Pickup only, no delivery | there is no delivery flow, which avoids temperature control in transit |

### The storage windows (pilot defaults)

| Stored as | Max time from preparation to “eat by” |
|---|---|
| Room temperature | **2 hours** |
| Kept hot (60 °C or above) | 4 hours |
| Refrigerated (5 °C or below) | 24 hours |
| Shelf-stable (bakery, packaged) | 48 hours |

The 2-hour room-temperature figure follows widely used guidance (the WHO *Five Keys to Safer Food* says
cooked food shouldn't be left at room temperature for more than about 2 hours, and to keep hot food above
60 °C and cold food below 5 °C). The other numbers are **conservative pilot defaults chosen by FoodLoop**,
not regulations. Agree real values with each kitchen's Food Safety Supervisor and set them in `.env`.

What this means for the business: lunch cooked at 11 am and left at room temperature is **not** sellable at
3 pm. The model works best for food kept in a bain-marie, chilled food, bakery items, and surplus sold
right after service. The pilot should measure how much surplus actually fits these windows.

## Compliance considerations (India)

1. **Every kitchen needs FSSAI registration or a licence.** FoodLoop stores the number, type and expiry,
   shows the number on every listing, and an admin checks it on FoSCoS before approval.
2. **FoodLoop itself, as a platform.** Published guidance on *e-commerce food business operators* says
   platforms should list only registered or licensed food businesses, display their FSSAI numbers, have
   agreements with sellers, and hold their own licence (sources describe a central licence). Some of this
   comes from a 2017 draft and secondary summaries, so **confirm before charging money**.
   ([USDA GAIN summary of the 2017 guidelines](https://gain.fas.usda.gov/Recent%20GAIN%20Publications/FSSAI%20Publishes%20Guidelines%20for%20Operations%20of%20E-Commerce%20FBOs_New%20Delhi_India_2-24-2017.pdf),
   [Lexplosion overview](https://lexplosion.in/the-legal-landscape-for-e-commerce-food-business-operators/),
   [FSSAI e-commerce advisory coverage](https://www.foodtechbiz.com/food-safety-and-traceability/fssai-issues-advisory-to-strengthen-food-safety-in-ecommerce-sector))
3. **Allergens.** The FSS (Labelling and Display) Regulations, 2020 require allergen declarations on
   *packaged* food (cereals containing gluten, peanuts, tree nuts, soy, milk, egg, fish and others; check the
   gazette for the full list). Canteen meals usually aren't packaged, but FoodLoop requires a declaration
   for every listing anyway, never claims “allergen-free”, and tells customers with severe allergies to check
   with the kitchen. ([FSSAI labelling FAQ](https://mail.fssai.gov.in/upload/uploadfiles/files/FAQ_Labelling_Display_01_11_2023.pdf))
4. **Donating unsold food.** If a later phase sends leftovers to NGOs, the FSS (Recovery and Distribution of
   Surplus Food) Regulations, 2019 apply to donors and food recovery organisations.
   ([text on Casemine](https://www.casemine.com/act/in/5f5f11aa9fca195c05cce574))
5. **Consumer protection.** Once FoodLoop operates commercially, the Consumer Protection (E-Commerce) Rules,
   2020 apply: show seller details and full prices, publish a refund/cancellation policy, and name a
   grievance contact.
6. **Personal data.** Under the Digital Personal Data Protection Act, 2023, collect the minimum and get clear
   consent. FoodLoop doesn't store customers' allergies or health data.
7. **Permissions.** For the pilot, get written permission from the canteen operator and, on a campus, the
   college administration. Agree in writing that the kitchen is responsible for the food and handles
   payment directly. In the MVP, FoodLoop never touches money.

## Incident process (pilot)

1. A customer reports a problem (WhatsApp/phone during the pilot; in-app reports come in Phase 2).
2. The admin **suspends** the kitchen if there is any safety doubt. Listings disappear and open
   reservations are cancelled with the reason.
3. Record what happened, talk to the kitchen, and decide together whether to reinstate it (the admin can
   re-approve).
