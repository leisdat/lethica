# Dual-theme token discipline (light mode ≠ dark mode inverted, verified 2026-08-28)

Context: a dark-first "Electric Mint on Deep Navy" UI shipped with a light theme that
was just the dark token block with colors flipped. User verdict: "mode terang itu
terlalu polos dan gk enak diliat". The redesign that satisfied them is a reusable
checklist for ANY theme-token CSS system.

## Bugs that almost always ship with inverted light themes
1. **Themed text on hardcoded dark panels.** A hero/banner with hardcoded navy
   background + child text using `var(--text)` = dark-on-dark in light mode. Rule:
   any panel with hardcoded brand colors must define its own guaranteed-on-color for
   text (or get a full per-theme override including text roles).
2. **Neon glows that vanish on white.** `rgba(brand, .18)` glow is invisible on #FFF.
   The light theme reads "polos" because its signature effect disappears.
3. **Shadow scales carried over from dark.** `rgba(0,0,0,.5)` blocks on white look
   dirty/cheap. Light premium = layered soft shadows.

## The fix pattern (proven)
- **Adaptive tokens via color-mix.** Define glow/border/tint tokens ONCE in `:root`
  against the theme's primary:
  `--glow-sm: 0 1px 2px rgba(16,24,40,.05), 0 0 12px color-mix(in srgb, var(--primary) 20%, transparent);`
  Then per-theme overrides become almost unnecessary for effects — they follow
  `--primary` automatically. Sweep ALL hardcoded brand rgba out of component rules
  (nav active glow, badges, progress bars, toggles, chips) into these tokens or
  inline `color-mix(... var(--primary) N%, transparent)`.
- **Light gets its own identity, not dimmed dark.** Concretely: slightly tinted bg
  (#EEF2F8, not #F4F6FA-flat), tinted surfaces, layered shadows
  (`0 1px 2px ... , 0 6px 20px rgba(16,24,40,.07)`), white shimmer tint for
  skeletons, deepened brand gradient so white button text stays readable.
- **Contrast math is non-negotiable for small text.** A vivid accent like
  emerald-500 (#0E9F77) on white is only ~3.9:1 — below WCAG AA for the small
  colored text it's usually used on. Use the 700-step (#047857 ≈ 5.5:1) for
  `--primary` text/badges; keep the vivid tone only inside gradients/buttons where
  it's large or white-on. Same for button gradients: check the LIGHTEST stop against
  the on-color (4.1:1 → 6.5:1 after deepening).
- **Verify served, not local.** After CSS edits, fetch the CSS over HTTP from the
  running server and assert the new tokens exist + old ones are gone + braces
  balance (reusable script pattern: scripts/verify_light_css.py in
  extension-hub-pro). A static-file server without cache headers serves edits
  immediately; extension workers idle-terminate so no restart needed there either.
