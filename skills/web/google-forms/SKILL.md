---
name: google-forms
description: Use when parsing Google Forms headlessly (extract/submit).
version: 1.0.0
---

# Google Forms programmatic parsing

Use when a Google Forms link (forms.gle/... or docs.google.com/forms/d/e/...) must be read, mined for questions, or submitted — especially when `web_extract` returns only the title/shell because the real content is JS-loaded.

## Key discovery: content lives in embedded JSON

The form's questions, options, entry IDs, images, and closed-form status are all in a single JS global in the page HTML:

```html
<script>var FB_PUBLIC_LOAD_DATA_ = [null, [...], ...];</script>
```

So the workflow is: **curl the form HTML → regex the JSON blob → walk the structure**. No browser, no JS execution, no authentication needed for public forms.

## Step-by-step

1. **Fetch the HTML with a mobile UA** (forms.gle short links redirect fine):
   ```bash
   curl -sL "<form_url>" -H "User-Agent: Mozilla/5.0 (Linux; Android 13) Chrome/120.0 Mobile Safari/537.36" -o form.html
   ```
2. **Extract the JSON** (note the space before `=` and the trailing `;`):
   ```python
   m = re.search(r'FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.*?\])\s*;', html, re.DOTALL)
   data = json.loads(m.group(1))
   ```
3. **Navigate the structure** (verified against a live form):
   - `data[1][0]` → form title
   - `data[1][1]` → `items` array (every question + section header)
   - `data[1][7]` → `[None, "..."]`; if it contains "no longer accepting responses" / "automatically close", **the form is closed** — skip submission
   - Each item is `[qid, title, None, type_code, ...]`:
     - type `0` = short text (entry id at `item[4][0][0]`)
     - type `2` = multiple choice; **options are at `item[4][0][1]`** as a list of `["option text", null, null, null, 0]` — NOT at `item[4]` directly (that was the initial parse mistake)
     - type `6` / `8` = section headers (no answers)
     - images (if any) at `item[9]` as `[["s-blob-v1-IMAGE-xxxx", null, [w,h,0]]]`

## Submission (open forms only)

POST `application/x-www-form-urlencoded` to:
```
https://docs.google.com/forms/d/e/<FORM_ID>/formResponse
```
with `entry.<entry_id>=<value>`, plus `fbzx` (hidden input in the HTML), `pageHistory`, `fvv`.

Closed forms return **HTTP 400** with body text containing "no longer accepting responses" — that 400 is the closed-state signal, not a bad-payload error. Verify by grepping the response HTML for that phrase rather than guessing at payload format.

## Pitfalls

- `web_extract` / naive page fetch returns only the shell title → always go to the embedded JSON.
- `s-blob-v1-IMAGE-*` blob IDs are **NOT** direct image URLs. Guesses like `drive.google.com/uc?id=...` or `/forms/.../blob/<id>` return 404/400. Resolving them needs a real browser render (the `lh*.googleusercontent.com` URL is built client-side). Don't burn time trying URL patterns.
- The blob IDs are ~11 chars and look like Drive file IDs — they are not; 404s confirm this.
- A form that auto-closes (owner set it, e.g. "automatically close by <owner>@gmail.com") is permanent — no amount of payload fixing will submit.

## Scripts

- `scripts/extract_questions.py` — run: `python3 extract_questions.py <form_url>`; dumps title, closed-status, and every question with options, ready for solving or answer-mapping.
