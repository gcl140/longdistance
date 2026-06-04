# Lisa — Design System

> Netflix-inspired streaming UI for a long-distance watch-party app.
> This file is the single source of truth for visual decisions. Match it.

## Design principles

1. **Cinematic & dark-first.** Black/near-black canvas, content (posters, video, faces) provides the color. UI chrome stays out of the way.
2. **One red.** A single saturated red is the only brand accent — used for the logo, primary actions, and focus. Never introduce a second accent color.
3. **Edge-to-edge.** Hero billboards and content rows bleed to the viewport edges. Generous horizontal padding (`px-4 md:px-12`), not boxed containers, on the app surface.
4. **Motion is subtle and physical.** Hover = gentle scale (`1.08`), nav fades on scroll, no bouncy/springy gimmicks.

## Color tokens

Defined in the Tailwind CDN config in each base template.

| Token | Hex | Use |
|---|---|---|
| `netflix-red` | `#E50914` | Logo, primary buttons, focus ring, active accents |
| `netflix-red` (hover) | `#b20710` | Button hover (`hover:bg-netflix-red/90`) |
| `netflix-dark` | `#141414` | App background |
| `netflix-black` | `#000000` | Solid nav on scroll, deepest surfaces |
| input surface | `#333333` | Form inputs (`bg-[#333]`) |
| `maroon` (legacy) | aliased → `#E50914` | Back-compat token so older markup turns red automatically |

Text: `text-white` primary, `text-white/70`–`/90` secondary, `text-gray-400`/`netflix-gray` muted.

## Typography

- **Body / UI:** Inter (`font-sen` / `font-karla`) — 400–800.
- **Display (hero titles):** Playfair Display (`font-playfair`) — used only for billboard `<h1>`.
- Loaded via Google Fonts. Headings are bold/extrabold and tight (`leading-none`, negative tracking on the wordmark).

## Logo

Wordmark only: **LISA** in `netflix-red`, Inter extrabold, uppercase, `letter-spacing:-.04em`. No icon lockup required.

## Core components

| Component | Spec |
|---|---|
| **Top nav** | `fixed`, transparent over hero → fades to `netflix-black` after 40px scroll (Alpine `scrolled`). Red wordmark left, links center-left, search/bell/profile right. |
| **Billboard hero** | ~85vh backdrop image, left-gradient + bottom-gradient fade (`.nf-hero-fade`), display title, short synopsis, **▶ Play** (white) + **ⓘ More Info** (translucent) buttons, maturity chip. |
| **Content row** | Horizontal scroller (`.row-scroller`, hidden scrollbar). Cards `nf-card` scale to `1.08` on hover with shadow; poster/landscape art with gradient title overlay. |
| **Auth card** | Centered `bg-black/75 rounded-md shadow-2xl`, dark backdrop image with top/bottom black gradient (falls back to `#141414`). |
| **Inputs** | `bg-[#333]`, transparent border, red focus ring (`0 0 0 2px rgba(229,9,20,.6)`), left icon, optional eye-toggle on password fields. |
| **Primary button** | `bg-netflix-red`, white semibold, `rounded`, `hover:bg-netflix-red/90`. |
| **Toasts** | Toastify, top-right; green/red/amber/blue by message tag (error = brand red). |

## Iconography

Font Awesome 6.4 (`fas`/`fab`/`fa-solid`). Eye / eye-slash for password reveal, play/info on hero, search/bell/caret in nav.

## Implementation notes

- **Tailwind via CDN** today (fast iteration). If/when build tooling lands, port the config block to `tailwind.config.js` unchanged.
- **Don't** reintroduce the old maroon/Playfair "Voima" charity styling — that brand is retired. The app is **Lisa**, Netflix-styled.
- Keep `[x-cloak]{display:none}` for Alpine-toggled elements.
- `static/images/` is currently empty — components must degrade gracefully when images 404 (solid dark bg, picsum/seeded placeholders for posters).
