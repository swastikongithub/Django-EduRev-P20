# Branding: the official LPU logo

The product uses the official Lovely Professional University seal. The project owner supplied it
as `static/img/lpu_logo.png`: a 2000x2000 PNG, round, transparent outside the circle. It is
committed unchanged as the master. It has not been redrawn, traced, recoloured, cropped, or
replaced by any other artwork, and no logo was downloaded from elsewhere.

## Renditions

Serving the 164 KB master at 30 pixels on every page would waste bandwidth, and browsers and
phones need specific icon sizes. `scripts/brand_renditions.py` therefore derives these files from
the master. It only resizes, with Lanczos resampling, and the iOS icon additionally places the
seal on an opaque white square, because iOS renders transparency as black.

| File in `static/img/brand/` | Size | Used for |
|---|---|---|
| `mark.png` | 128x128 | the seal in the UI, shown at 30 to 56 CSS px |
| `favicon.ico` | 16, 32 and 48 px | browser tab, bookmarks |
| `favicon-32.png` | 32x32 | browser tab (PNG) |
| `apple-touch-icon.png` | 180x180 on white | iOS home screen |
| `icon-192.png`, `icon-512.png` | 192x192 and 512x512 | web app manifest (`/site.webmanifest`), Android |

If the university supplies a new master, replace `static/img/lpu_logo.png`, run
`python scripts/brand_renditions.py`, and commit the results.

## Where the seal appears

`apps/core/branding.py` finds the renditions at start-up (`brand` context processor). These
places use them:

| Place | Template | Treatment |
|---|---|---|
| Desktop navigation rail | `base.html` → `components/brandmark.html` | 34 px seal in the white brand tile. The link is named "LPU Reserve home", so the image has empty alt text |
| Mobile top bar | `base.html` → `components/brandmark.html` | 30 px seal in the small tile; empty alt for the same reason |
| Sign-in page hero | `accounts/login.html` | 56 px seal beside "LPU Reserve" on the saffron panel. The panel is decorative (`aria-hidden`) |
| MFA enrolment and verification | `accounts/mfa.html` (one template for both) | seal in the card header, alt "Lovely Professional University" |
| Error pages (403, 404, 500) | `errors/error.html` | seal, alt "Lovely Professional University" |
| Printed door signs | `manage/door_qr.html` | seal beside "LPU Reserve" |
| Browser tab, bookmarks, home-screen icons | `components/brand_head.html`, `/site.webmanifest` | favicon set, touch icon, manifest icons |

The profile page has no brand element, and there is no site-wide footer to brand. The sign-in
page already ends with "Lovely Professional University, Phagwara" in text.

### Favicon

The seal is square, so using it whole as a favicon keeps the correct aspect ratio. At 16 px its
lettering is not legible, but the orange and black disc remains recognisable. The favicon set is
derived from the seal without cropping or simplification; a simplified mark for tiny sizes
would need to come from the university. These files are the only favicon: the earlier placeholder
`static/img/favicon.svg` has been removed, and no icon link or manifest entry is emitted for a file
that is not present.

## Static files

The renditions are ordinary static files. `runserver` serves them in development. In production,
`collectstatic` gives them content-hashed names at image build time, and WhiteNoise serves them
with immutable caching, so replacing the logo needs a new deploy and never shows a stale copy.
`tests/test_branding.py` checks the sizes, the placements, the alt text, the manifest and the
fallback to the placeholder.
