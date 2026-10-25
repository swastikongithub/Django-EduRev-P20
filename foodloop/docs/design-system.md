# FoodLoop design system

**Direction:** a dark charcoal kitchen with warm orange, like a menu board at night. Charcoal surfaces, one
bright orange for actions and highlights, round "plate" photos of real food, and green only where it means
something. Every token lives in `frontend/src/index.css` (`@theme`).

**Tokens are named by role, not colour** (`page`, `panel`, `fg`, `brand`...). A redesign changes the values
in `index.css` and nothing else. Until October 2026 the names were colours (`cream`, `ink`, `leaf`), which
stopped making sense when the palette changed; they were replaced everywhere in one go.

## Colour

| Role | Token | Hex |
|---|---|---|
| Deepest bands: home hero, footer, cards on orange | `night` | `#0E0D0C` |
| Page background | `page` | `#151412` |
| Cards, headers | `panel` | `#1D1B19` |
| Inputs, chips, hover, nested surfaces | `raised` | `#282522` |
| Borders and dividers | `line`, `line-strong` | `#34302C`, `#4A453F` |
| Headings and main text | `fg` | `#F8F4EF` |
| Body text | `fg-soft` | `#D2CBC2` |
| Secondary text, hints, placeholders | `fg-muted` | `#A1998F` |
| Brand: buttons, links, prices, active states | `brand-500` (hover `brand-400`) | `#FF7518` |
| Orange text on dark | `brand-400`, `brand-300` | `#FF8C3A`, `#FFA96A` |
| Orange tints behind badges and notices | `brand-950`, `brand-900` | `#261409`, `#3B1D0B` |
| Veg marks, success, "live" | `leaf-*`, `veg` | |
| Pending, paused, attention | `turmeric-*` | |
| Collected | `info-*` | |
| Errors, removed, low stock | `danger-*` | |

**Bright orange takes dark text** (`text-night`), never white: white on `#FF7518` is only 2.5 : 1.

Measured contrast (WCAG AA needs 4.5 : 1 for text):

| Pair | Ratio |
|---|---|
| `fg` on `page` / `panel` | 16.8 / 15.7 |
| `fg-soft` on `panel` / `raised` | 10.7 / 9.5 |
| `fg-muted` on `panel` / `raised` | 6.1 / 5.4 |
| `brand-400` on `page` / `panel` | 7.9 / 7.4 |
| `night` on `brand-500` / `brand-600` | 7.2 / 5.7 |
| `night` at 80% on `brand-500` (text in the orange band) | 5.4 |
| `brand-200` on `brand-950` (info notices) | 11.8 |
| `leaf-300` on `leaf-950`, `turmeric-300` on `turmeric-950`, `info-300` on `info-950`, `danger-300` on `danger-950` (status pills) | 10.1, 10.6, 9.0, 9.7 |

## Typography

- **Headings:** Bricolage Grotesque (variable, with optical sizes): modern, warm and highly legible.
  Weight 700, slight negative tracking, `text-wrap: balance`.
- **Body and UI:** Inter (variable).
- Hero headline is about 68px on desktop and 42px on phones. Section titles are 36–42px. Body text is
  15–17px.

## Components (`@utility` classes)

| Class | Use |
|---|---|
| `btn-primary` | the one main action in a view (orange with a soft orange glow, dark text) |
| `btn-secondary` | secondary action (charcoal with an outline that turns orange on hover) |
| `btn-accent` | the single biggest call to action on a screen (orange gradient with a glow) |
| `btn-ghost`, `btn-danger` | quiet and destructive actions |
| `btn-sm`, `btn-lg` | sizes. All buttons are at least 44px tall for touch |
| `card` | `panel` surface, 20px radius, hairline `line` border, soft shadow |
| `input`, `label`, `hint`, `field-error` | forms with visible focus rings and error states |
| `chip` | filter toggles and tabs (`aria-pressed`); the pressed one is an orange pill |
| `badge`, `StatusPill` | statuses and labels |
| `eyebrow` | small uppercase label above a section title |
| `container-page` | page width (max 1280px) and responsive side padding |
| `plate` | a round food photo with a thick ring and deep shadow, as in the hero and the dish cards |

**Radii:** cards 20px, feature panels 28–40px, images inside cards 16–20px, buttons fully rounded.
**Shadows:** `shadow-soft` at rest, `shadow-lift` on hover.

## Shared React pieces

| Component | Where | Use |
|---|---|---|
| `PageHeader` | `components/ui.tsx` | the panel band at the top of My reservations, the kitchen dashboard, the listing form and admin: eyebrow, title, description, actions and tabs. `narrow` lines it up with a form-width page |
| `BusyLabel` | `components/ui.tsx` | button text that swaps to a spinner and “Saving…”-style text while a request runs |
| `useToast()` | `components/Toast.tsx` | short confirmations (“Reservation confirmed”, “Listing published”) and errors. Bottom of the screen on phones, bottom right on desktop, read out by screen readers, gone after a few seconds |
| `StatTile`, `Notice`, `EmptyState`, `ErrorState`, `Skeleton`, `Tabs` | `components/ui.tsx` | numbers, messages, empty, error and loading states |
| `ListingCard`, `DishCard`, `MenuRow`, `KitchenCard` | `components/` | the full meal card (Explore Meals, closing soon), the compact dish card with a round photo (home page), a menu line, a kitchen card |
| `MealImage`, `Photo` | `components/` | every food picture |

**Charts:** the kitchen dashboard's “Last 7 days” card is the only chart. Each bar is a share of the portions
listed (listed → reserved → collected) in orange (`brand-500`) on a dark orange track (`brand-950`), with
the number written beside it. It uses the kitchen's real numbers only, and shows a
plain message instead of empty bars when nothing has been listed yet.

**Phones:** on a meal page the order is photo → name, price and Reserve → food details. A bottom bar with the
price and a Reserve button appears once the reserve panel scrolls out of view.

## Backgrounds and the home page

- **Page:** charcoal (`page`) with a warm orange glow in the top-right and bottom-left corners and a fine dot
  texture, fixed behind the content (`body` in `index.css`). `index.html` paints the same charcoal before
  the stylesheet loads, so there is never a white flash.
- **Night bands** (`night`) for the home hero, the Menu, Kitchen and About headers and the footer.
- **Home hero:** a big round thali on a dashed orbit with an orange glow, three small dish plates floating
  around it, a chip with the live dish and kitchen counts, and the real "closing soon" deal.
- **Our dishes:** orange pill tabs per meal type (with live counts) over a grid of `DishCard`s.
- **Why choose FoodLoop:** four icon cards for the safety rules.
- **Orange wave band** (`Wave` + `brand-500`) for the kitchen pitch, with dark benefit cards on it.
- **Why it matters:** a round photo on a tilted orange shape.
- Utilities: `glass` (frosted panel on dark), `text-sunrise` (orange gradient text, one phrase per
  section at most), `plate` and `rail` (horizontal swipeable rows).
- There are **no star ratings or customer testimonials**: FoodLoop has no reviews yet, and invented ones
  would mislead people.

## Live and moving parts (`src/components/Live.tsx`)

| Piece | Use |
|---|---|
| `Countdown` | “Closes in 24:13”, ticking every second in the last hour, orange in the last 30 minutes |
| `CountUp` | real numbers counting up once when they scroll into view |
| `Reveal` | sections rising gently into place the first time they're seen |
| `LiveDot` | a pulsing green dot next to anything that updates by itself (green means live, so it stays green) |
| `DealTicker` | an endless, hover-to-pause ticker of current deals on the dark hero |
| `Rail` | swipeable rows (closing soon, kitchens) with arrow buttons on desktop |
| `ConnectionBanner` | says whether the server or the database is down, and reconnects by itself |

Everything shows real API data only, and all motion stops for people who prefer reduced motion.

**Layout rule:** every responsive grid starts with `grid-cols-1`, so long text can never push a phone
layout sideways (a grid without it sizes its column to the content).

## Photography (`src/lib/photos.ts`, `src/components/Photo.tsx`)

- 41 real food photos from Adobe Stock (none AI-generated), stored as WebP at 480/800/1200 px (the hero
  also has 1600 px). They
  are served with `srcset`/`sizes`, lazy-loaded below the fold, and the hero has `fetchpriority="high"`.
- A meal without its own photo gets a representative photo matched by its name (biryani → biryani), or
  else by meal type. It is always labelled **“Representative image”**. A kitchen's own upload always wins.
- If a photo is missing or fails to load, it swaps to FoodLoop's illustration of the same meal type, so
  there's never a broken image.
- Photos aren't committed, because of the licence. See `docs/image-credits.md`.

## Motion

Cards lift by 4px and their image zooms about 5% on hover. Sections rise in gently, and the hero example
cards float slowly. Smooth scrolling is used for in-page links. All motion is switched off for people who
prefer reduced motion (`prefers-reduced-motion`).

## Honesty rules in the UI

- No invented impact numbers. Statistics are cited (UNEP 2024), and FoodLoop's own numbers will come only
  from measured pilot data.
- Sample listings carry a **“Sample data”** badge, and the landing page says so above them.
- The hero only shows real numbers and a real listing. The "Reserved" card in How it works is a drawing of
  the screen, not a real order.
