# Frontend reader pitfalls from Xyra API (Aug 2026)

## loading="lazy" inside scroll containers

Images inside a `div` with `overflow-y: auto` (a custom scroll container) that use the native `loading="lazy"` attribute may **never load** in mobile browsers (Chrome Android, Brave). The native lazy-loading mechanism uses `IntersectionObserver` against the root viewport, NOT the scroll container. If the scroll container is shorter than the viewport, all images below the initial visible area are assumed to be below the fold and get `loading="lazy"` applied — but they never trigger because the observer never sees them enter the viewport.

Fix: omit `loading="lazy"` (or use `loading="eager"`) for images inside custom scroll containers. For chapter readers with 10-15 images, eager loading adds negligible overhead (~1-2MB total).

## Single tap handler (pointerup) for mobile

Using both `touchend` and `click` handlers on the same element causes double-fire on Android browsers: one tap toggles open then immediately closed. The user perceives needing "3 lucky taps" to succeed. Fix: use a single `pointerup` event handler — it fires once for mouse, touch, and pen. Add CSS `touch-action: manipulation`, `-webkit-tap-highlight-color: transparent`, and ensure tap targets are ≥48px.

## Skeleton shimmer over spinner

A skeleton shimmer animation (gradient sweep with `background-size: 200%` + `animation: shimmer 1.4s`) is more professional than a spinner. User explicitly rejected generic designs saying "kurang profesional" — skeleton shimmer, cover fade-in, smooth transitions, and scroll-to-top buttons are floor-level quality expectations.