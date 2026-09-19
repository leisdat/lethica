---
name: reference-image-web-design
description: Use when recreating a website from a poster or screenshot.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows, android]
tags: [design, html, screenshot, poster, visual-reference, fidelity]
---

# Reference-Image Web Design

Use this class-level skill when a user asks for a website that looks like a supplied poster, screenshot, advertisement, game key art, or other visual reference.

## Core rule

Match the reference's **composition before its mood**. A page with the right colors but the wrong silhouette, typography scale, panel arrangement, or overlap order is not a successful recreation.

## Workflow

1. Inspect the reference at full resolution before coding. Record:
   - canvas ratio, background color, paper/grain treatment
   - header/logo positions
   - headline wording, font character, scale, line breaks, stroke/fill treatment
   - every major artwork panel's bounds, rotation, clipping, depth order, and focal point
   - badges, ticket/event blocks, labels, footer marks, and decorative rules
   - mobile behavior implied by the reference
2. Check whether the original image or separate assets are available locally. If they are, use them directly for the first fidelity pass, preferably with `object-fit`, crops, masks, and overlays. Do not substitute abstract CSS gradients for supplied artwork when the user wants close visual similarity.
3. Decide the surface archetype. Posters are usually an editorial/teaser surface: one dominant composition, not a generic hero plus feature-card grid.
4. Build the structural silhouette first: large type, image collage, panel geometry, and event/ticket block. Only then refine colors, texture, shadows, and motion.
5. Keep the implementation original where required: preserve general layout principles and visual hierarchy, but replace protected branding, copy, and assets unless the user has rights and explicitly requests exact use.
6. Make the first output visually inspectable. Prefer a single self-contained HTML artifact for quick iteration; add responsive rules without destroying the desktop composition.
7. Verify file existence, HTML parsing, JavaScript syntax if present, and local serving. If no browser/screenshot inspection is available, say so explicitly. Never claim a high-fidelity visual match based only on static syntax checks.

## Fidelity checklist

Before delivery, compare the artifact against the reference in this order:

- overall silhouette at thumbnail size
- dominant title placement and proportion
- number, angle, and overlap of artwork panels
- event/ticket block location and shape
- background tone and texture
- type width, tracking, outline, and line breaks
- secondary labels and footer alignment
- responsive crop and readability

If the result is clearly far from the reference, rebuild the composition instead of polishing colors or adding generic effects. A user saying “not like the photo” is a composition failure signal.

## Asset and limitation handling

If the vision inspection tool fails or the reference cannot be read closely, do not invent certainty. Use the user-provided description only for a rough scaffold, explain that close visual matching requires a readable image or extracted assets, and ask for a higher-resolution upload when artwork identity is important. If proceeding anyway, label the result as an inspired mockup rather than a close recreation.

## Anti-patterns

- Do not turn a poster reference into a standard centered landing-page hero.
- Do not replace a distinctive collage with generic mountains, gradients, or unrelated abstract shapes and call it close.
- Do not omit the reference's title treatment, panel geometry, ticket block, or paper/print character.
- Do not report “verified” as visual verification when only parser/server checks ran.

## Supporting detail

See `references/poster-recreation-notes.md` for the validated lessons from a reference-image recreation session.
