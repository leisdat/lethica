# Terse Regex Cookbook

Regex yang dipake di `terse_filter()` Lethica + variasi policy wrapper yang sering muncul di output LLM. Tujuannya: strip prefix useless + defensive wrapper biar hemat token (200-500 per refusial).

## Core terse_filter (verified pass 6/6 cases)

```python
import re

def terse_filter(text):
    if not text:
        return text
    drop_patterns = [
        # system wrapper tags (treated as background noise)
        r"<system-reminder>.*?</system-reminder>",
        r"\[SystemNote\].*?\[/SystemNote\]",
        r"\[ContentFiltered\]",
        r"\[Refused\]",
        r"<redacted>.*?</redacted>",
        # refusal wrappers
        r"I'm sorry,? but[^.]{0,100}\.",
        r"As an? (AI|language model|assistant)[^.]{0,80}\.",
        # politeness prefix (token waste)
        r"Sure!?\s*",
        r"Of course!?\s*",
        r"I'd be happy to[^.]{0,40}\.\s*",
    ]
    out = text
    for p in drop_patterns:
        out = re.sub(p, "", out, flags=re.DOTALL | re.IGNORECASE)
    return out.strip()
```

## Test cases (verified 2026-09-08)

| Input | Output | Saved |
|-------|--------|-------|
| `"Sure! Let me help you with that."` | `"Let me help you with that."` | 1 word politeness |
| `"Of course! I'll do it."` | `"I'll do it."` | 2 words politeness |
| `"I'm sorry, but I cannot help with that request."` | `""` | full refusal strip |
| `"As an AI language model, I don't have access."` | `""` | full disclaimer strip |
| `"[Refused] <redacted>content</redacted>"` | `""` | system wrapper strip |
| `"<system-reminder>be safe</system-reminder>execute this"` | `"execute this"` | system noise strip |

## Common wrapper patterns (extended)

### System-level noise
```regex
<system-reminder>.*?</system-reminder>
\[SystemNote\].*?\[/SystemNote\]
\[ContentFiltered\]
\[Refused\]
<redacted>.*?</redacted>
\[Safety filter triggered\]
```

### LLM politeness prefix (English)
```regex
Sure!?\s*
Of course!?\s*
I'd be happy to[^.]{0,40}\.\s*
Glad to help\.?\s*
Happy to (?:help|assist)[^.]{0,30}\.\s*
Certainly!?\s*
Absolutely!?\s*
```

### Refusal wrappers
```regex
I'm sorry,? but[^.]{0,150}\.
I (?:cannot|can't|am unable to|don't have (?:the )?ability to)[^.]{0,100}\.
As an? (?:AI|language model|assistant)[^.]{0,100}\.
Unfortunately,? I[^.]{0,80}\.
I (?:must|have to) (?:decline|refuse)[^.]{0,50}\.
```

### Indonesian politeness
```regex
Baik,? saya akan[^.]{0,40}\.
Tentu,? saya[^.]{0,40}\.
Dengan senang hati[^.]{0,40}\.
Mohon maaf,? (?:saya|tidak bisa)[^.]{0,80}\.
```

### Inline safety reminder
```regex
Safety reminder:[^\n]{0,200}
Note: this (?:might|could) be (?:sensitive|restricted)[^\n]{0,200}
```

## Where to apply

1. **Pre-save** (in agent loop): apply `terse_filter` to LLM reply BEFORE appending to `messages` history — saves storage + future context window.
2. **Pre-render** (display): apply before rendering to terminal/Panel — avoids showing 500 tokens of "I cannot..." in front of the user.
3. **NOT pre-send** (prompt engineering): don't pre-filter the user's prompt — user input is sacred, just respond.

## Performance

`terse_filter` is O(n*m) where n=text length, m=number of patterns. For typical LLM reply (200-2000 tokens = 800-8000 chars), takes <1ms on Termux. Fine for inline use, no need to cache.

## Edge cases

- **Empty input**: return empty (skip regex loop).
- **Markdown code block**: terse_filter might strip parts of legitimate `<` characters if not inside `<system-reminder>` — be careful with code review summaries. Solution: extract code blocks first, filter outside, re-insert.
- **Multilingual**: Indonesian politeness is rare in LLM output (most use English), but if needed, add `re.IGNORECASE` + language-specific patterns.

## Extending the filter

Add new patterns as you discover them in your specific model/provider. Pattern priority matters — put more specific (refusal wrappers) before generic (single "Sure!"). Order in `drop_patterns` list = first match wins per pattern.
