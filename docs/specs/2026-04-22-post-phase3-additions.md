# Post-Phase-3 Additions — Design Supplement

**Date:** 2026-04-22
**Status:** Shipped (documenting what was already built)

## Purpose

Phase 1/2/3 design docs describe the original scope. This supplement records features that were added after Phase 3 was approved, so the docs reflect what actually ships. Nothing here is a new proposal — it is a record of shipped code.

---

## 1. Rescan — refresh a stored practice from Google Places

### What it is

A way to re-pull the latest Google Places data (rating, reviews count, hours, etc.) for a practice already in the database, without re-running AI analysis.

### Backend

- `src/places.py` — new `get_place(place_id, fallback)` async helper that calls the Places Details endpoint (`GET https://places.googleapis.com/v1/places/{place_id}`) with the same field mask used by search. Skips Google and returns `fallback` when `place_id` starts with `mock_` or `real_` (seeded IDs) or when `GOOGLE_MAPS_API_KEY` is empty.
- `api/index.py`:
  - New endpoint `POST /api/practices/{place_id}/rescan` — 404 if not found, else refreshes from Google, upserts, returns the updated row.
  - Extended `AnalyzeRequest` with a `rescan: bool` field. When `rescan=true`, `POST /api/practices/{place_id}/analyze` refreshes from Google before running the AI pipeline.

### Frontend

- `web/lib/api.ts` — `rescanPractice(placeId)` helper.
- `web/app/page.tsx` — top-bar "Rescan" button that re-runs the last search query (faster than retyping).
- Practice cards pass `refresh: true` on Re-analyze, which sends both `force` and `rescan` to the analyze endpoint.

---

## 2. RingCentral click-to-call

### What it is

One-click call from practice cards and the Call Prep page. Tries the desktop/mobile RingCentral app first; falls back to RingCentral web if the app doesn't capture the deep link.

### Implementation

- `web/lib/ringcentral.ts` — normalizes phone numbers to E.164, builds three URLs (`rcmobile://` app link, web app URL, `tel:` fallback), and `openRingCentralCall(phone)` that attempts the app link with a ~900ms fallback timer to open the web URL if the app never took over (detected via `blur` / `visibilitychange`).
- `web/components/call-button.tsx` — wraps an `<a>` with the web URL for right-click usability but intercepts the click to call `openRingCentralCall`.
- Used in [practice-card.tsx](../../web/components/practice-card.tsx) and [practice-info.tsx](../../web/components/practice-info.tsx).

### Env var

- `NEXT_PUBLIC_RINGCENTRAL_WEB_APP_URL` (default `https://app.ringcentral.com`) — override for self-hosted RingCentral.

---

## 3. Multi-source review collection

### What Phase 2 specified

Google Places reviews only (up to 5 most relevant).

### What actually ships

`src/reviews.py` pulls from three sources and merges them:

1. **Google Places reviews** — `fetch_google_reviews(place_id)`. Up to 5 reviews via Place Details with field mask `reviews.text,reviews.rating,reviews.originalText`.
2. **First-party review pages** — crawls the practice website homepage for internal links matching `review|reviews|testimonial|testimonials|feedback`, then fetches up to 2 of those pages and extracts review-like sentences using keyword heuristics.
3. **Third-party review sites** — DuckDuckGo HTML search for `"<name> <city> <state> reviews"`, filtering result URLs by a known-domain allow-list (Yelp, Facebook, Healthgrades, Zocdoc, Birdeye, Rater8, Vitals, WebMD, RateMDs, Demandforce). Fetches up to 4 and extracts snippets.

All sources are deduplicated by `(source, normalized_text)`. `format_reviews_for_prompt()` groups snippets by source for the GPT prompt, which gets a much richer signal than Google Reviews alone.

### Notes

- Per-page snippet cap: 4. Only sentences 50–320 chars with at least one review-keyword (review, patient, staff, front desk, wait time, etc.).
- Strips `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>` before extraction.
- All fetches use a 10–12s timeout and the `HVSalesIntel/1.0` User-Agent.

---

## 4. OPENAI_MODEL setting

`src/settings.py` exposes `OPENAI_MODEL` (default `"gpt-4o"`). Both `analyzer.py` and `scriptgen.py` honor it — lets ops swap to `gpt-4o-mini` for cost or `gpt-4.1`/later without code changes.

---

## 5. Phase 3 item NOT shipped: Activity History

The Phase 3 spec included an "Activity History" section inside the notes panel on the Call Prep page, showing timestamped status changes (e.g., `Apr 17 — Script generated`). This was **not implemented**. The notes panel is notes-only. If/when built, it will need a separate `activity_events` table (or a JSON column) — the current schema only keeps the latest `status`, not a history.

---

## 6. Frontend state lives in a client component, not server components

Phase 1 spec said `page.tsx` would be a server component with server actions in `actions.ts`. Actual implementation is a single client component that holds practice state and calls the FastAPI backend directly via `web/lib/api.ts`. `actions.ts` was never created. All data fetching happens client-side with mock fallbacks.

This is simpler for a demo tool and avoids splitting mock logic across server/client. Not a regression — just a deviation from the original spec worth noting.

---

## 7. Storage API — one generic updater

Phase 3 spec proposed `update_practice_status`, `update_practice_notes`, `get_script`, `set_script`. Actual storage module ships one generic helper — `update_practice_fields(place_id, fields: dict)` — plus `update_practice_analysis` for the Phase 2 bulk update. All endpoints compose those two.

---

## Current env var matrix

| Var | Scope | Default | Notes |
| --- | --- | --- | --- |
| `GOOGLE_MAPS_API_KEY` | backend | `""` | Empty → mock search + no Google reviews |
| `SUPABASE_URL` / `SUPABASE_KEY` | backend | `""` | Empty → storage no-ops |
| `OPENAI_API_KEY` | backend | `""` | Empty → mock analysis + script |
| `OPENAI_MODEL` | backend | `"gpt-4o"` | Used by analyzer + scriptgen |
| `NEXT_PUBLIC_API_URL` | frontend | `""` | Empty → all API calls use client-side mocks |
| `NEXT_PUBLIC_RINGCENTRAL_WEB_APP_URL` | frontend | `"https://app.ringcentral.com"` | Self-hosted RC override |
