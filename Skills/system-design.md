# Phil — UI system design

Design spec for Phil (FreeCAD Voice Extension). Target: premium, restrained,
navy-led palette. Built in Python/Tkinter (tk.Frame + tk.Canvas), packaged
as a .app via PyInstaller. This doc is the source of truth for opencode
when updating UI code — implement components to match these tokens exactly,
don't introduce new colors ad hoc.

## Design principles

1. **One dominant color, one accent, one silent neutral.** Navy carries the
   UI's identity. Gold is used sparingly — status, key actions, highlights
   only. Grey never appears as a "brand" color, only as structural/text
   support. This restraint is what makes it read premium instead of busy.
2. **Flat surfaces.** No gradients, no drop shadows, no glow/blur effects.
   Depth comes from flat color contrast and spacing, not effects.
3. **Sentence case everywhere.** Labels, buttons, status text — never
   Title Case or ALL CAPS.
4. **Motion is functional, not decorative.** Animations (PulseRing,
   self-correction loading bar, planned transition animations) should
   communicate state changes, not add flourish.

## Color tokens

| Token | Hex | Role |
|---|---|---|
| `color-bg-canvas` | `#FFFFFF` | App background / light surfaces |
| `color-navy-900` | `#14213D` | Primary surface (header, panels), primary text on light bg |
| `color-navy-700` | `#1F2E52` | Hover/active state of navy surfaces |
| `color-gold-500` | `#C6A15B` | Accent — status badges, primary CTA, active/selected state |
| `color-gold-900` | `#412402` | Text placed on top of gold fills (never black) |
| `color-grey-400` | `#8A8D93` | Secondary text, borders, disabled state, dividers |
| `color-grey-200` | `#D8DAE0` | Hairline borders on light surfaces |
| `color-text-on-navy` | `#FFFFFF` | Primary text/icons on navy surfaces |
| `color-text-on-navy-muted` | `#9AA1B2` | Secondary text on navy surfaces (timestamps, hints) |
| `color-error` | `#B3261E` | Error state only — self-correction failures, build errors |
| `color-success` | `#2E7D32` | Success state only — successful build/render |

Rules:
- Gold never covers more than one element per screen at a time (one badge,
  one active button — not both simultaneously unless directly related).
- Grey is never used as a headline/brand color — text and structure only.
- Text on a colored fill always uses that fill's darkest token
  (`color-gold-900` on gold, `color-text-on-navy` on navy) — never plain
  black.

## Typography

- System sans throughout (no serif, no decorative fonts).
- Two weights only: regular (400) and medium (500). Avoid bold (700) —
  reads heavy against the flat, restrained palette.
- Sizes: 20px headers, 14px body/labels, 12px secondary/hint text.
- Sentence case always, no terminal punctuation on labels/buttons.

## Spacing & shape

- Base spacing unit: 4px. Common gaps: 8px, 12px, 16px, 24px.
- Corner radius: 8px for cards/panels, 6px for buttons/badges, pill
  (radius ≥ half height) only for the PulseRing widget and status dots.
- Border weight: 0.5px hairlines (`color-grey-200`) — never 1px+ unless
  emphasizing a focus/active state.

## Core components

### Header / status bar (navy surface)
- Background: `color-navy-900`
- App name left-aligned, `color-text-on-navy`, 15px medium
- Status badge right-aligned: `color-gold-500` bg, `color-gold-900` text,
  6px radius, states: `Ready`, `Building`, `Error` (error state swaps
  badge to `color-error` bg / white text — this is the one place gold
  is overridden)
- Secondary line below (optional): last build time, `color-text-on-navy-muted`, 12px

### PulseRing widget
- Existing animated widget — keep current animation logic, restyle fill
  to `color-gold-500` for active/processing state, `color-grey-400` for
  idle, `color-error` for failure state.
- No glow/blur — animate via scale/opacity steps only (flat-safe).

### Self-correction loading bar (just added)
- Track: `color-grey-200`
- Fill: `color-gold-500` while retrying, switches to `color-error` if the
  error-memory retry loop exhausts attempts, `color-success` on resolve.
- Label above bar: 12px, `color-grey-400`, e.g. "Retrying · attempt 2 of 5"

### Buttons
- Primary: `color-navy-900` bg, white text — reserve for one primary
  action per screen only.
- Secondary: transparent bg, `color-grey-200` border, `color-navy-900`
  text, hover → `color-bg-canvas` shade shift.
- Never use gold as a button fill except the single most important
  action on a screen (e.g. "Build").

### Cards / panels
- White bg, 0.5px `color-grey-200` border, 8px radius, no shadow.
- Section headers 14px medium `color-navy-900`, body 14px regular
  `color-grey-400` unless it's primary content.

## Pending implementation (this pass)

- [ ] Apply token set above across existing widgets (PulseRing, loading bar,
      header) — replace any hardcoded colors with the tokens in this doc.
- [ ] UI transition animations — state changes (idle → building → ready)
      should crossfade/slide using flat color steps, no blur.
- [ ] macOS compositing fix — tk.Frame + tk.Canvas pill shape currently
      needs `bg="systemTransparent"` with manually drawn pill geometry.
      Keep this workaround; just restyle fill colors to match tokens above.
- [ ] Real 3D thumbnails (v0.2, standalone) — thumbnail frame should use
      `color-grey-200` border, `color-bg-canvas` background, no accent
      color unless the thumbnail represents the currently active build.

## Out of scope for this pass

- No new color introduced outside this token set.
- No gradients, shadows, or glow effects, including for the "premium"
  goal — restraint is the mechanism, not added effects.
