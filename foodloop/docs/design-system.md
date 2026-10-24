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

## Photography (`src/lib/photos.ts`, `src/components/Photo.tsx`)

- Real food photos from Adobe Stock, stored as WebP at 480/800/1200 px (the hero also has 1600 px). They
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
