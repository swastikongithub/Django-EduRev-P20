# LPU Reserve design system

The interface is built from the inspected LPU portals (old UMS and the new studentums
portal) and then modernised. This page is the contract every screen follows.

## Identity

| Kept from LPU | Why | How it appears here |
|---|---|---|
| LPU orange (old UMS `#F68121`) | The single most recognisable brand cue | `--saffron-500` for fills, primary buttons, the left rail, flags. Orange *text* uses `--ember` for AA contrast. |
| Orange icon rail on the left (old UMS) | Instantly reads as "UMS" | `.rail` on desktop; a bottom tab bar on phones |
| Orange tab label on cards (old UMS "My Messages", "Happening") | Signature card treatment | `.panel--flagged` + `.flag` — used once or twice per screen, never on every card |
| VID / section profile block (both portals) | Identity students recognise | `.profile` chip in the top bar, `profilecard` on /me |
| Plus Jakarta Sans, navy ink, cool canvas (new portal) | Continuity with the current portal | `--font`, `--ink-900` text, `--canvas` background |
| Dark mode (new portal) | Students already use it | Tokens redefined under `prefers-color-scheme: dark` and `[data-theme=dark]` |

| Fixed | Old behaviour | Here |
|---|---|---|
| 11.5 px Arial everywhere | Hard to read | 15 px base, a real type scale, tabular numbers for times |
| Blocking pop-ups on load | Interrupts every visit | Never. Toasts for feedback; dialogs only when the user asks |
| Menus with hundreds of links | No hierarchy | Task-first navigation by capability |
| New portal deep-linking into legacy .aspx pages | Two products in one | One consistent product |

## Signature: the day strip

Time is the product, so every resource shows a miniature ribbon of its day: classes
(indigo hatch), bookings (slate), yours (orange), pending (orange hatch), maintenance
(amber stripes), blackouts (cross-hatch), closed (sunk grey). Use `{% daystrip schedule %}`
(compact) or `{% daystrip schedule compact=False %}` (with hour labels). Each state has a
pattern as well as a colour, so it reads without colour vision.

## Tokens (static/css/tokens.css)

Colour: `--saffron-*`, `--ember`, `--ink-*`, `--blue-*`, `--green-*`, `--red-*`, `--amber-*`,
`--indigo-*`; semantic `--canvas --surface --surface-2 --surface-sunk --line --line-strong
--text --text-2 --text-3 --link`. Never hard-code hex in templates or page CSS — use tokens,
so dark mode works.

Space: `--s1..--s16` (4 px grid). Radius grows with size: `--r-xs` inputs-small → `--r-sm`
buttons/inputs → `--r-md` small cards → `--r-lg` panels → `--r-xl` hero panels.
Elevation: panels are flat (1 px `--line` border, no shadow); only floating things
(dialogs, toasts, hovered resource cards) use `--shadow-float`.

## Components (static/css/app.css)

- Layout: `.pagehead` (h1 + intro p + actions), `.grid .grid-2/3/4`, `.split` (main + 380 px side),
  `.split--wide-side`, `.split--left` (290 px filters + main), `.stack` (`--gap`), `.row`
  (`--gap`, `.row--between`, `.row--wrap`), `.sticky-side`, `.section-head`.
- Buttons: `.btn` + `--primary` (one per view), `--ink`, `--blue`, `--ghost`, `--danger`,
  `--danger-solid`, `--success`; sizes `--sm --lg --xl`; `--block`, `--icon`. Labels say exactly
  what happens ("Approve", "Book 10:00–11:30") — never "Submit". No arrows appended.
- Forms: `.field` > `label` + `.input/.select/.textarea` (+ `.hint`, `.error`), `.form-grid`
  (+ `.span-2`), `.chips` / `.chip` (checkbox/radio inside), `.seg` segmented control,
  `.checkrow`, `.inputgroup` (leading icon).
- Panels: `.panel` (+ `--flush`, `--sunk`, `--warm`, `--pad-lg`), `.panel__head`, `.panel__foot`,
  `.panel--flagged` + `<span class="flag">{% icon "x" %}Label</span>` (`.flag--ink`, `.flag--blue`).
- Data: `.tablewrap` > `table.table` (`.num` right-aligned tabular; `a.rowlink`), `.list`,
  `.kv` (dl), `.kpi` (`__label __value __delta.up/.down`), `.meter` (`.is-mid .is-high`),
  `.badge` (`--success --danger --pending --live --info --warn --class --plain`),
  `{% status_badge booking %}`, `.legend` + `.swatch--<state>`.
- Feedback: `.notice` (`--success --danger --warn`, default info) with an icon and a `<strong>`
  lead sentence; Django messages render as toasts automatically; `.empty` (`__icon`, h3, p,
  one action) for empty states — say what to do next, never just "No data".
- Dialogs: `<dialog class="sheet">` with `.sheet__head` / `.sheet__body`; open with
  `data-open="id"`, close with `data-close`. Destructive forms use `data-confirm="Sentence"`
  (needs a `#confirm-dialog` sheet on the page, see bookings/pass.html).
- Media: `{% resource_photo r "sm" %}` (480 px) / `"lg"` (960 px).
- Icons: `{% icon "name" [size] [cls] %}` from the Lucide subset in static/img/icons.svg
  (list the available ids with `grep -o 'id="i-[^"]*"' static/img/icons.svg`).
- Filters: `|hm` (14:05), `|dayname` (Today / Tomorrow / Mon 12 Oct), `|duration` (1 h 30 min),
  `|pct`, `|inr` (₹12,34,567).

## Rules

1. **Server-side permissions first.** Hidden buttons are cosmetic; every view checks
   capabilities (`apps.core.manage_views.staff_required(...)`) and object scope.
2. **CSP:** `script-src 'self'` — no inline `<script>` and no `onclick=`. Behaviour goes in
   `static/js/*.js` using `data-*` hooks; htmx attributes are fine (`allowEval` is off).
3. **Explain, don't just disable.** Every unavailable slot, refused action or empty list says
   why and what to do instead.
4. **One primary action per view.** Sentence-case copy, active voice, no ALL-CAPS labels, no
   "A · B · C" metadata strings, no exclamation marks.
5. **Mobile is designed, not shrunk.** Check 360 px: tables scroll inside `.tablewrap`,
   side panels stack, touch targets ≥ 40 px.
6. **Motion answers actions** (selection pulse, booking tick, sheet open) and respects
   `prefers-reduced-motion` (handled globally).
7. **Accessible by default:** labelled inputs, `aria-current` for nav, visible focus,
   `role="status"`/`aria-live` for async results, colour never the only signal.
