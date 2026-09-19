# Aggregator API review checklist (lessons from user code-reviews)

User performs senior-level JSON reviews of the API output and catches subtle data
bugs. Run this checklist before presenting scraper/API work for review.

## 1. Rank/panel contamination
Ranked homepages with multiple panels (mingguan/harian/total) inside one section:
bounding a panel scrape by "next <section>" pulls sibling panels in. Symptom in
output: rank sequence 1..20 then restarts at 13,16,18 with tiny view counts.
Fix: bound by every sibling marker, excluding the target panel.
Verify: ranks strictly 1..N, zero duplicates per panel.

## 2. Signed URL hygiene
- Emit `coverPath` (stable, no signature), `coverProvider`, and
  `coverExpiresAt` (parsed from X-Amz-Date + X-Amz-Expires) alongside any signed cover.
- Normalize `&amp;` → `&` on EVERY URL-producing code path; verify zero occurrences
  of `&amp;` in final output (a single missed branch breaks image loads).

## 3. Zero vs null statistics
Sites emit `"totalViews":"0"` when stats aren't computed yet. Convert to null;
null = unavailable, not zero views. Never present literal 0 as view count.

## 4. Pairing integrity
Cross-check scraped (title, chapter, timestamp) triples against ground truth parsed
independently from saved HTML. Mismatched pairing reads as "random order" to users.

## 5. Response envelope
Every endpoint: `{status:"success", source:"<site>", ...meta, data}` — consumers
must be able to tell provenance in multi-source aggregators.
