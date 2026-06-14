# Mariposa Studio — Brand Identity

> **Club Paper** · *Warm. Crafted. Unhurried.*

This document is the brand half of the design. The system half — how these
choices become reusable UI — lives in [DESIGN.md](DESIGN.md). Every value here is
expressed as a token in [`design.py`](design.py); change it there and the whole
app follows.

---

## 1. Personality

**Warm. Crafted. Unhurried.**

Three words the whole product must keep expressing:

- **Warm** — a paper-cream canvas, white cards, soft shadows. The UI feels like
  good stationery, not a cockpit.
- **Crafted** — a serif display voice (Fraunces) over a precise grotesque
  (Inter), pill-shaped controls, a 4px grid. Nothing is approximate.
- **Unhurried** — one bottle-green accent used with restraint. The UI never
  shouts; your footage and prompts are the loud thing, not the chrome.

The north star is the "members' club" polish of The Padel Society — editorial
serif headlines, cream paper, bottle green — and a deliberate rejection of the
"AI default" look (rainbow gradient cards, emoji icons, generic Bootstrap
chrome).

---

## 2. Logo & wordmark

The mark is a **butterfly** — *mariposa* — drawn as a clean, symmetrical vector
silhouette: two large rounded upper wings, two smaller lower wings, a slim body
and a pair of curled antennae. It's a single-colour shape (`currentColor`), so
it reads on dark **and** light without edits, and stays recognizable down to
16px because it's one silhouette, not a scene.

| Asset | File | Use |
|---|---|---|
| Logomark | [`brand/logomark.svg`](brand/logomark.svg) | App, window, favicons. Uses `currentColor` → works on dark **and** light. |
| Wordmark (dark/green bg) | [`brand/wordmark-dark.svg`](brand/wordmark-dark.svg) | Paper-white serif. READMEs on dark, green surfaces. |
| Wordmark (light bg) | [`brand/wordmark-light.svg`](brand/wordmark-light.svg) | Ink serif + green "Studio". Print, light docs. |
| App icon | rendered by [`make_icon.py`](make_icon.py) → `AppIcon.icns` | Dock, Finder, Launchpad. |

**Clear space:** keep padding ≥ half a wing-width around the mark.
**Don't:** recolor the wings a second brand color, add a drop shadow to the
glyph, stretch it, or place it on a busy photo without a scrim.

### App icon concept
A bottle-green squircle with the paper-white butterfly — recognizable down to
16px because it's one shape + one color, not a scene. Regenerate any time with
`./venv/bin/python src/make_icon.py` (macOS + Windows). The icon **is** the
logomark: `make_icon.py` rasterises `brand/logomark.svg` directly, so the two
can never drift.

---

## 3. Color palette

One accent, a disciplined neutral ramp, and minimal semantics. Each token has a
job — we don't add a color without a reason.

### Accent — "Court" (the only brand color)
| Token | Hex | Role |
|---|---|---|
| `GREEN` | `#046C4E` | Primary action, focus ring, selection, signal dot |
| `GREEN_HI` | `#0B7F5E` | Hover |
| `GREEN_DIM` | `#03543C` | Pressed |
| `GREEN_TINT` | `rgba(4,108,78,.10)` | Soft fill behind selected items |

*Why one accent?* A single signal color makes the primary action unmistakable on
every screen and keeps the product feeling like one tool, not five. Bottle green
reads established and calm — a club crest, not a notification.

### Neutrals — "club paper"
A warm cream-to-white ramp. Depth comes from soft shadow, never from glow.

| Token | Hex | Role |
|---|---|---|
| `PAPER_CANVAS` | `#F6F3EC` | App background (warm cream) |
| `PAPER_WELL` | `#0E1F19` | Deepest well — the console stays a dark pit |
| `PAPER_PANEL` | `#FBFAF6` | Sticky bars, top chrome |
| `PAPER_CARD` | `#FFFFFF` | Cards, tiles, inputs |
| `PAPER_CARD2` | `#F1EDE3` | Hover / selected surface |
| `PAPER_RAISED` | `#FFFFFF` | Menus, popovers (deeper shadow, not darker) |
| `PAPER_LINE` | `#E5E0D3` | Hairline dividers |
| `PAPER_LINE2` | `#CFC9B9` | Stronger / hover borders |

The old dark-theme names (`INK_*`, `IRIS_*`) remain in `design.py` as
back-compat aliases pointing at these tokens.

### Text — 4-step legibility ramp (green-cast ink)
`TXT_HI #13241D` (headings) · `TXT_BODY #33423A` (body) · `TXT_DIM #67756C`
(labels) · `TXT_FAINT #98A39A` (placeholder) · `TXT_DISABLED #BDC5BC`.

### Semantic (used sparingly)
`SUCCESS #067647` · `WARNING #B45309` · `DANGER #D92D20`. Each also has a ~10%
tint for backgrounds.

### Per-tool hues (wayfinding only)
Each tool owns one hue, used **only** as a small icon-chip tint + glyph color —
never as a full gradient card. Deepened so each reads on white at equal weight.

| Tool | Hue | Icon (Lucide) |
|---|---|---|
| Flow Cropper | `#4F46E5` indigo | `scissors` |
| Captions | `#0284C7` sky | `captions` |
| Extract Frame | `#0F766E` teal | `film` |
| Camera Prompts | `#B45309` amber | `camera` |
| Script Animator | `#7C3AED` violet | `clapperboard` |

---

## 4. Typography

**Display:** **Fraunces** (OFL, bundled in [`brand/fonts/`](brand/fonts)) — the
serif voice for big titles only (hero titles, app-bar titles, the wordmark).
It carries the "club" character.

**UI:** **Inter** (OFL, bundled) for everything else. Both families are loaded
at startup by `design.load_fonts()` via `QFontDatabase` — in Qt a font must be
registered before the stylesheet is applied, or the family name silently falls
back to a system font.

**Mono:** **JetBrains Mono** → `SF Mono` → `Menlo`. Used for the console and any
technical / numeric value.

```
FONT_UI      = "Inter", -apple-system, "SF Pro Text", "Helvetica Neue", Arial, sans-serif
FONT_DISPLAY = "Fraunces", "Playfair Display", Georgia, serif
FONT_MONO    = "JetBrains Mono", "SF Mono", "Menlo", "Consolas", monospace
```

### Type scale
| Role | Size / Weight | Tracking | Use |
|---|---|---|---|
| Display | 30 / 600 serif | -0.3 | Home & Settings hero |
| Title | 20 / 700 | -0.3 | Big numbers, panel titles |
| Heading | 15–16 / 600–700 | -0.2 | Top-bar title (serif), card titles |
| Body | 13 / 400 | 0 | Default text |
| Label | 12 / 600 | 0 | Field labels, buttons |
| Caption | 11 / 500 | 0 | Secondary meta |
| Micro | 10 / 700 | +1.5, UPPERCASE | Section eyebrows |

Serif only at display sizes; below ~16px everything is Inter — small serif
rendering is where the elegance breaks.

---

## 5. Iconography

Real vector icons from **[Lucide](https://lucide.dev)** (ISC licensed), rendered
through Qt's SVG engine and recolored from tokens — see `svg_icon()` in
`design.py`. **Zero emoji** anywhere in the UI. Icons are stroke-based, 2px, with
round caps. The full set lives in [`brand/icons/`](brand/icons).

---

## 6. Shape language

Controls are **pills**: outline at rest (white fill, `PAPER_LINE2` border),
solid Court green with white text when selected/primary. Cards and panels use
12–16px radii. This is the reference brand's "simple, clean tab" pattern, and
it is the default for every segmented control, chip and button.

---

## Extending the brand
1. Need a new color? Add it as a token in `design.py` with a one-line "role"
   comment. If you can't name its job, don't add it.
2. New tool? Pick a hue + Lucide icon name in `TOOL_ACCENTS` / `TOOL_ICONS`.
3. Keep the rule: **one accent, paper everything else, pills not boxes, serif
   only for display sizes.**
