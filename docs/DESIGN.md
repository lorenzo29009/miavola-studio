# Mariposa Studio — Design System

How the [brand](BRAND.md) becomes real UI. If you only read one section, read
**"The one rule"** at the bottom.

This is a **PySide6 (Qt for Python)** desktop app — there is no web framework or
component library. The "design system" is therefore three things, all in
[`design.py`](design.py):

1. **Tokens** — every color, font, size, radius, shadow and duration.
2. **An icon system** — `svg_icon()` renders [Lucide](https://lucide.dev) SVGs.
3. **A stylesheet** — `build_stylesheet()` turns tokens into the app-wide QSS
   (Qt's CSS-like styling), keyed by widget *object names*.

`studio.py` imports from `design.py` and **never hard-codes a color or size**.
To re-skin the entire app, edit tokens in `design.py` — nothing else changes.

---

## 1. Tokens (the single source of truth)

```python
from design import GREEN, PAPER_CARD, TXT_DIM, R_MD, svg_icon, tint, ...
```

| Group | Examples | Notes |
|---|---|---|
| Neutrals | `PAPER_CANVAS` … `PAPER_LINE2` | 8-step warm cream-to-white ramp; each step has one job |
| Text | `TXT_HI`, `TXT_BODY`, `TXT_DIM`, `TXT_FAINT`, `TXT_DISABLED` | green-cast ink legibility ramp |
| Accent | `GREEN`, `GREEN_HI`, `GREEN_DIM`, `GREEN_TINT`, `GREEN_LINE`, `GREEN_FG` | the only brand color ("Court") |
| Semantic | `SUCCESS`, `WARNING`, `DANGER` (+ `_TINT`) | used sparingly |
| Tools | `TOOL_ACCENTS`, `TOOL_ICONS` | one hue + one Lucide name per tool |
| Type | `FONT_UI`, `FONT_DISPLAY`, `FONT_MONO`, `TYPE` | Inter UI, Fraunces display, scale roles: display→micro |
| Layout | `SPACE`, `R_SM/MD/LG/XL/FULL` | 4px grid; pill controls, 12–16px cards |
| Depth/Motion | `SHADOW_*`, `DUR_FAST/BASE/SLOW` | whisper-soft shadows; OutCubic |

> **Back-compat aliases.** The dark-theme names (`INK_CANVAS…INK_BORDER2`,
> `IRIS_*`) and the original aliases (`BG, PANEL, CARD, CARD_HI, BORDER, TEXT,
> TEXT_DIM, TEXT_FAINT, ACCENT, ACCENT_HI, OK_COLOR, ERR_COLOR`) map onto the
> new tokens so existing code keeps working. New code should prefer the
> descriptive names (`PAPER_CARD`, `GREEN`, …).
>
> **Fonts must be loaded before styling.** `design.load_fonts()` registers
> `brand/fonts/*.ttf` via `QFontDatabase`; `main()` calls it before
> `setStyleSheet`, otherwise Qt silently falls back to system fonts.

Helpers: `tint(hex, alpha)` → an `rgba(...)` string for QSS tints;
`brand_pixmap(stem, width, color)` → renders a `brand/*.svg` (home lockup).

---

## 2. Icon system

```python
svg_icon(name, color=TXT_HI, size=18, stroke=2.0) -> QIcon   # for buttons
svg_pixmap(name, color, size)                      -> QPixmap # for QLabel
```

- Reads `brand/icons/<name>.svg` (authentic Lucide, ISC license).
- Recolors `currentColor` → `color`, renders @2x for retina crispness, caches by
  `(name, color, size, stroke)`.
- **No emoji anywhere.** Need a new glyph? Drop the Lucide SVG into
  `brand/icons/` and call `svg_icon("its-name", ...)`. Download:
  `curl -fsSL https://unpkg.com/lucide-static@latest/icons/<name>.svg -o brand/icons/<name>.svg`

The legacy `chevron_icon()` / `arrow_icon()` helpers in `studio.py` now just
delegate to Lucide, so every back button and primary action shares one source.

---

## 3. Primitives (reusable, object-name styled)

Qt styles widgets by **`objectName`**. Set the name; the QSS does the rest. The
catalogue (all defined in `build_stylesheet()`):

| Primitive | `objectName` | Where |
|---|---|---|
| **OS shell** | | |
| System bar | `SystemBar` (+ `Wordmark`, `Clock`, `SpotlightPill`) | Launcher top |
| App icon | `AppIcon` / `_AppBadge` (painted) + `AppName` | Launcher desktop |
| Recent chip | `RecentChip` (+ `RecentName/Meta`) | Launcher "Recenti" |
| Spotlight | `SpotlightScrim` / `SpotlightPanel` / `SpotlightField` / `SpotlightItem` | ⌘K overlay |
| App bar | `AppBar` (Home `HomeBtn` + accent dot + `AppTitle`) | every opened app |
| **Inside apps** | | |
| Card surface | `Card` | forms, status, panels |
| Drop zone (hero input) | `DropZone` (`#DropTitle/#DropMeta`, live thumbnail) | the primary file/folder of a tool |
| Segmented control | `Segmented` (reuses `ModeToggle/ModeBtn`) | AI\|UGC, mode, language |
| Toggle | `Switch` (painted, per-app hue) | dry-run, "Refine with Gemini" |
| Preset chips | `ChipGroup` (editable value + `PillBtn` presets) | frame count / interval |
| Label-on-top field | `Field` (+ `grid_2col`) | dense 2-column form grids |
| Status panel | `StatusTitle` / `StatusDetail` / `StatusProgress` | job-runner result area |
| Primary button | `PrimaryBtn` | the one green "go" action of each app |
| Secondary / Ghost / Danger | `SecondaryBtn` / `GhostBtn` / `DangerBtn` | Browse / details / Stop |
| Console (collapsible) | `Console` | mono log behind "Show details" |
| Segmented toggle | `ModeToggle` + `ModeBtn` | Simple/Custom, Single/Combine |
| Filter pill | `PillBtn` | Camera Prompts categories |
| Selection chip | `SelectionChip` (+ `ChipTag/Remove`) | Camera multi-select |
| Prompt card | `PromptCard` (`[selected="true"]`) | Camera grid |
| Float panel | `FloatPanel` + `Float*` | Animator presenter |
| Toast | `Toast` | copy confirmations |

To add a styled element: give it an existing `objectName`, or add a new rule in
`build_stylesheet()` using tokens (never a literal hex).

---

## 4. Information architecture — "Mariposa OS"

The app is a small **operating system for creators**, not a launcher of cards.
Five tools, each opened as its own full-canvas **app**. The connective tissue is
the OS itself — a launcher, a system search, and shortcuts — never a sidebar.

- **Launcher (`LauncherPage`, the "Scrivania")** — the desktop. A system bar
  (logomark + wordmark · centered **Spotlight** pill · live clock · settings),
  a serif time-of-day greeting, the five **app card tiles** (solid hue badge +
  white Lucide glyph, name, tagline — the reference app's home pattern), and a
  **Recenti** strip surfacing recent `exports/` files.
- **Opening an app** — the launcher recedes (zoom + fade) and the app fills the
  canvas. Each app has an `AppBar`: a **Home** button, the app's **accent dot**,
  the title, and the primary action — wearing the app's own hue.
- **Spotlight (`⌘K`)** — the system launcher/switcher: type to jump to any app,
  `↑↓` + `Enter` to choose. Reinforces the OS feel and gives power-user speed.
- **Returning** — Home button or `Esc`; the app shrinks away to reveal the
  launcher. `⌘1…⌘5` jump straight to an app.

### The three app archetypes (don't force one shape on all)
- **Job runner** (Flow Cropper, Captions, Extract Frame) — `ToolPage`: an input
  `Card` (`FormRow`s, drag-and-drop) → primary action in the `AppBar` → a **status
  panel** (`StatusTitle` + dot, indeterminate `StatusProgress`, latest-line detail,
  a result action, and a collapsible "Show details" log). Flow: **input →
  action → result**.
- **Browser** (Camera Prompts) — `PillBtn` filters + search → sectioned
  `PromptCard` grid. Click copies; "Combine" stacks `SelectionChip`s for Gemini.
- **Transform** (Script Animator) — `ModeToggle` (Simple/Custom) → script
  `Card` → "Build storyboard" → segments + a draggable `FloatPanel` presenter.

### States (every job-runner app)
- **Empty** — placeholder copy + status "Ready · Output will appear here."
- **Loading** — status "Running…" in green + indeterminate progress, Stop shown.
- **Done / Error** — "Done" (green) / problem (red, auto-opens the log) + a
  result action (Open folder / Reveal .srt).
- **Keyboard** — `⌘K` Spotlight · `⌘1–5` open apps · `Esc`/Home back · arrows
  navigate the launcher · `Ctrl+Return` runs the active app · drag-and-drop input.

---

## 5. Motion & depth
- **App open/close:** a ~230ms zoom + fade in the OS shell (`MainWindow._transition`),
  OutCubic — the launcher recedes, the app shrinks away. Robust because it snapshots
  the *visible* widget.
- Depth comes from white-on-cream layering + a single whisper-soft shadow —
  **never** a colored glow.

---

## The one rule

**One system accent (Court green). Each app owns one hue for its own
action/identity. Everything else paper. Pills, not boxes; serif only at display
sizes. No gradient content cards, no emoji.** Differentiate with iconography
and hierarchy, not color.

### Extending
1. **New tool:** subclass `ToolPage` (job runner) or build a bespoke `QWidget`
   that starts with an `AppBar`. Add `("Name", "key", Class, available)` to
   `specs` in `MainWindow`, plus `"key": hue` / `"key": "lucide-name"` in
   `TOOL_ACCENTS` / `TOOL_ICONS` and a line in `APP_TAGLINES`. It then appears on
   the launcher, in Spotlight, and gets a `⌘n` shortcut automatically.
2. **New token:** add it to `design.py` with a one-line role comment.
3. **New component:** give it an `objectName` + a token-based rule in
   `build_stylesheet()`. No one-off inline styles.
