# Mobile reader: let the BODY scroll, not a container (the "ke-potong" saga)

From Xyra API /comic reader, Aug 2026. Symptoms seen together across user reports:
chapter images stop exactly at the viewport bottom (not their natural bottom) → after
switching to container scroll, "can't click chapters / images never show".

## Root causes, in order found

1. **`position:fixed` + `overflow-y:auto` custom scroll containers are unreliable on Chrome Android** (Brave too). Combined with deprecated `-webkit-overflow-scrolling:touch`, images get clipped at the viewport edge, and `100vh` mis-sizes on mobile (it includes the URL-bar area).
2. **`document.body.style.overflow='hidden'` also blocks scrolling inside fixed children on Android** — never toggle body overflow to lock the page behind an overlay.
3. **`getElementById('main')` on a bare `<main>` tag returns `null`** → `null.style.display = 'none'` throws TypeError → the whole openCh handler dies → "clicking a chapter does nothing, images never render". The `$()` id-helper only works on elements that actually have that id — add `id="main"` to the tag or use `document.querySelector('main')`.

## The reliable architecture: reader is a full-page section, body scrolls natively

```css
.reader{position:absolute;top:0;left:0;right:0;min-height:100dvh;background:#000;display:none;z-index:200}
.rpages img{width:100%;max-width:100%;height:auto!important;display:block;object-fit:contain;margin:6px 0}
```

```js
function openCh(...){ $('reader').style.display='block'; $('main').style.display='none'; window.scrollTo(0,0); ... }
function closeReader(){ $('reader').style.display='none'; $('main').style.display=''; window.scrollTo(0,0); }
```

## Rules that prevent the whole class of "cut off at the bottom" reports

- Never put `height:100vh`, `max-height`, or `object-fit:cover` on reader images — each one produces exactly that report.
- `height:auto!important` on reader images guards against other rules overriding it.
- `100dvh` (dynamic viewport height) is the mobile-correct unit; `@supports not (height:100dvh)` fallback to `100vh`. With body-scroll architecture `min-height` is enough and container height stops mattering.
- After ANY reader refactor, run `node --check` on the extracted `<script>` block (extract to a temp file first). Two of the three regressions this session were silent JS crashes that only showed as "can't click / nothing renders" — syntax check catches them before the user does.
