# Pilot kit: validate FoodLoop before building more

The riskiest questions aren't technical. **Do kitchens really have safe surplus, regularly? Will they sell
it cheaply? Will people actually turn up to collect it?** Answer them with 1–2 kitchens, a WhatsApp group
and a spreadsheet, for about ₹500–2,000, before spending on hosting or launch.

| File | Use it for |
|---|---|
| [interview-guide.md](interview-guide.md) | 20–30 minute conversation with a canteen / mess / PG manager |
| [customer-survey.md](customer-survey.md) | 4-minute Google Form for students and employees |
| [daily-log-template.csv](daily-log-template.csv) | one row per kitchen × day × meal slot × item (import into Google Sheets) |
| [portion-weights-template.csv](portion-weights-template.csv) | weighing a few portions, so “kg saved” is measured rather than guessed |
| [reservations-log-template.csv](reservations-log-template.csv) | pilot reservations before the app goes live |

The daily-log columns match the planned Phase 3 `daily_food_logs` table, so pilot data imports straight into
the analytics work. Every row carries `data_source = pilot_manual`, which keeps real data separate from
synthetic sample data.

## Four-week plan

| Week | What happens |
|---|---|
| 0 | Run the interviews and the survey (aim for 100+ responses). Get **written permission** from the kitchen operator, plus the college if on campus. Agree: eligible items and storage, the longest time from cooking to “eat by”, prices, the pickup point, and that the **kitchen collects payment directly** (UPI/cash). |
| 1 | **Baseline week, no selling.** The kitchen logs prepared / sold / leftover / what happened to leftovers every day. Weigh 5–10 portions of common items. Without this week, any “waste avoided” number is a guess. |
| 2–3 | **Pilot.** At a fixed time after service (e.g. 2:45 pm), post the surplus in an opt-in WhatsApp Channel/Community, or use this app with the kitchen approved. People reserve and get a pickup code. Log everything. |
| 4 | Analyse, re-interview the kitchen and 5–10 customers, then decide using the rule below. |

**Pilot safety rules:** only food kept hot (60 °C+), chilled (5 °C or below), or shelf-stable; never food that
was served on a plate or returned. Every post states prepared time, veg/non-veg, allergens and eat-by.
Pickup only. Customers are told to eat it straight away.

## Metrics: set the bars before the pilot starts

These are suggested starting points, not industry standards. Adjust them to your situation **before** you
see the data.

| Area | Metric | Formula (from the sheet) | Suggested bar |
|---|---|---|---|
| Supply | Surplus days | days with ≥1 listable batch ÷ pilot days | ≥ 60% |
| Supply | Portions listed / kitchen / day | mean of `listed_qty` | ≥ 8–10 |
| Demand | Sell-through | `reserved_qty ÷ listed_qty` | ≥ 50% |
| Demand | Collection rate | `collected_qty ÷ reserved_qty` | ≥ 80% |
| Demand | Repeat customers | customers with ≥2 pickups ÷ all customers | ≥ 30% |
| Operations | Kitchen staff time | minutes per day (ask) | ≤ 15 |
| Safety | Incidents; listings with full labels | count; % | 0; 100% |
| Value | Kitchen wants to continue (and would pay later) | interview | yes |

### Decision rule
- **Continue** (finish Phase 2, run a bigger pilot): the bars are met at one or more kitchens for two weeks
  in a row, with zero safety incidents.
- **Pivot A, strong demand but irregular surplus:** move towards pre-orders and demand forecasting that
  help kitchens cook the right amount in the first place.
- **Pivot B, steady surplus but weak demand:** change time, price or location, or route surplus to
  registered food-recovery NGOs.
- **Stop or rethink:** kitchens won't take part, or the safe window is too short for the surplus they
  actually have.

## Waste numbers you can defend

- **Food redirected (kg)** = collected portions × measured grams per portion (from `portion-weights`).
  Report it as a range (min–max of the weighings), not a single precise number.
- Call it **waste avoided** only after applying the share of leftovers that was *actually being thrown
  away* in the baseline week. Food that would have become a staff meal or a donation wasn't wasted anyway.
- Don't add CO₂ or “meals saved for the planet” numbers unless you cite the conversion factor and label
  the result as an estimate.

## Business watch-outs

- **Commission alone is thin.** Illustrative arithmetic, not a forecast: 15 meals/day × ₹40 × 26 days =
  ₹15,600/month recovered for one kitchen. At a 10% commission, FoodLoop would earn about ₹1,560/month from
  it. Waste analytics and forecasting for kitchens may be the stronger product.
- **Incentive conflict.** If FoodLoop works too well, kitchens might cook extra on purpose. Track surplus as
  a % of food prepared, cap how much can be listed, and only allow listings after service.
