# FoodLoop design system

**Direction:** premium food delivery meets sustainable living. That means warm cream and white surfaces,
forest green for actions, soft sage for calm sections, orange only as a small accent, and real food
photography. Every token lives in `frontend/src/index.css` (`@theme`). Change a value there and the whole
app follows.

## Colour

Token names stayed the same through the redesign (`leaf` = forest green, `saffron` = orange accent), so
older pages pick up the new palette automatically.

| Role | Token | Hex | Contrast checked |
|---|---|---|---|
| Page background | `cream-100` | `#FAF6EE` | |
| Cards, inputs | white | `#FFFFFF` | |
| Calm sections | `sage-100` / `sage-50` | `#E5EDE1` / `#F2F6F0` | |
| Primary action, links | `leaf-600` | `#1D6A43` | white on it: 6.6 : 1 |
| Hover / strong text | `leaf-700` | `#165536` | on cream: 8.2 : 1 |
| Deep sections, footer | `leaf-900` | `#0B2E1C` | cream on it: 13.7 : 1 |
| Body text | `ink-900` / `ink-700` | `#141D18` / `#33403A` | |
| Secondary text | `ink-500` | `#5D6862` | on cream: 5.4 : 1, on white: 5.8 : 1 |
| Discount badge, urgency text | `saffron-600` | `#AD4C0C` | white on it ≈ 5.2 : 1 |
| Decorative accent (underline, icons) | `saffron-400`, `turmeric-400` | | not used for small text |

All text pairs meet **WCAG AA** (4.5 : 1). Orange is never used for body text on pale orange.

## Typography

- **Headings:** Bricolage Grotesque (variable, with optical sizes): modern, warm and highly legible.
  Weight 700, slight negative tracking, `text-wrap: balance`.
- **Body and UI:** Inter (variable).
- Hero headline is about 68px on desktop and 42px on phones. Section titles are 36–42px. Body text is
  15–17px.

## Components (`@utility` classes)

| Class | Use |
|---|---|
| `btn-primary` | the one main action in a view (green, lifts slightly on hover) |
| `btn-secondary` | secondary action (white with border) |
| `btn-accent` | main action on dark green sections (turmeric) |
| `btn-ghost`, `btn-danger` | quiet and destructive actions |
| `btn-sm`, `btn-lg` | sizes. All buttons are at least 44px tall for touch |
| `card` | white, 20px radius, hairline border, soft shadow |
| `input`, `label`, `hint`, `field-error` | forms with visible focus rings and error states |
| `chip` | filter toggles (`aria-pressed`) |
| `badge`, `StatusPill` | statuses and labels |
| `eyebrow` | small uppercase label above a section title |
| `container-page` | page width (max 1280px) and responsive side padding |

**Radii:** cards 20px, feature panels 28–40px, images inside cards 16–20px, buttons fully rounded.
**Shadows:** `shadow-soft` at rest, `shadow-lift` on hover.

## Shared React pieces

| Component | Where | Use |
|---|---|---|
| `PageHeader` | `components/ui.tsx` | the sage band at the top of My reservations, the kitchen dashboard, the listing form and admin: eyebrow, title, description, actions and tabs. `narrow` lines it up with a form-width page |
| `BusyLabel` | `components/ui.tsx` | button text that swaps to a spinner and “Saving…”-style text while a request runs |
| `useToast()` | `components/Toast.tsx` | short confirmations (“Reservation confirmed”, “Listing published”) and errors. Bottom of the screen on phones, bottom right on desktop, read out by screen readers, gone after a few seconds |
| `StatTile`, `Notice`, `EmptyState`, `ErrorState`, `Skeleton`, `Tabs` | `components/ui.tsx` | numbers, messages, empty, error and loading states |
| `ListingCard`, `MealImage`, `Photo` | `components/` | meal cards and every food picture |

**Charts:** the kitchen dashboard's “Last 7 days” card is the only chart. Each bar is a share of the portions
listed (listed → reserved → collected) in one green (`leaf-500`, checked for contrast against white) on a
pale green track, with the number written beside it. It uses the kitchen's real numbers only, and shows a
plain message instead of empty bars when nothing has been listed yet.

**Phones:** on a meal page the order is photo → name, price and Reserve → food details. A bottom bar with the
price and a Reserve button appears once the reserve panel scrolls out of view.

## Backgrounds

- **Page:** a bright warm white (`cream-50`) with soft saffron, green and turmeric glows and a fine dot
  texture, fixed behind the content (`body` in `index.css`).
- **Dark green bands** (`leaf-900`) for the home hero, Menu, Kitchen and About headers: the same glows and a
  white dot texture. On the home page the header floats over the hero with light text until you scroll.
- **Sage bands** (`sage-50`, via `PageHeader`) for dashboards, forms, FAQ and Contact.
- Utilities: `glass` (frosted panel on dark green), `text-sunrise` (orange-to-turmeric text, one phrase per
  section at most) and `rail` (horizontal swipeable rows).

## Live and moving parts (`src/components/Live.tsx`)

| Piece | Use |
|---|---|
| `Countdown` | “Closes in 24:13”, ticking every second in the last hour, orange in the last 30 minutes |
| `CountUp` | real numbers counting up once when they scroll into view |
| `Reveal` | sections rising gently into place the first time they're seen |
| `LiveDot` | a pulsing green dot next to anything that updates by itself |
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
- Hero widgets are labelled **“Example listing”**.
