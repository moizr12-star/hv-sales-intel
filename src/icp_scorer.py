"""ICP (Ideal Customer Profile) scorer for Health & Virtuals.

Replaces the generic GPT-derived lead_score with a deterministic, transparent
score (0-100) computed from explicit ICP signals — geography, specialty fit,
practice size proxy, rating opportunity (inverse: lower stars = more pain),
review depth, website presence, plus the AI-derived hiring + urgency signals.

The output also includes a per-dimension breakdown so SDRs can see *why* a
lead scored what it did.
"""

from typing import Any


def score_icp(practice: dict[str, Any]) -> dict:
    """Score a practice 0-100 against the H&V ICP. Returns dict with `total`
    and `breakdown` (list of `{label, score, max, reason}` rows).
    """
    breakdown: list[dict] = []

    # ---------- 1. Geography (max 10) ----------
    state = (practice.get("state") or "").upper().strip()
    if state == "FL":
        breakdown.append({
            "label": "Geography",
            "score": 10,
            "max": 10,
            "reason": "Florida — initial focus market",
        })
    elif _is_us_state(state):
        breakdown.append({
            "label": "Geography",
            "score": 5,
            "max": 10,
            "reason": f"US ({state}) — operating geography, not focus market",
        })
    else:
        breakdown.append({
            "label": "Geography",
            "score": 0,
            "max": 10,
            "reason": "Outside US operating geography",
        })

    # ---------- 2. Specialty fit (max 15) ----------
    cat = (practice.get("category") or "").lower()
    if cat in ("mental_health", "primary_care"):
        breakdown.append({
            "label": "Specialty fit",
            "score": 15,
            "max": 15,
            "reason": f"Core specialty ({cat.replace('_', ' ')})",
        })
    elif cat in ("dental", "chiropractic"):
        breakdown.append({
            "label": "Specialty fit",
            "score": 10,
            "max": 15,
            "reason": f"Parallel clinical specialty ({cat})",
        })
    elif cat == "urgent_care":
        breakdown.append({
            "label": "Specialty fit",
            "score": 5,
            "max": 15,
            "reason": "Urgent care — healthcare-adjacent, not primary ICP",
        })
    else:
        breakdown.append({
            "label": "Specialty fit",
            "score": 3,
            "max": 15,
            "reason": f"Outside primary ICP ({cat or 'unknown category'})",
        })

    # ---------- 3. Practice size (review count proxy → ICP category) ----------
    rc = int(practice.get("review_count") or 0)
    if rc < 50:
        breakdown.append({
            "label": "Practice size",
            "score": 15,
            "max": 15,
            "reason": f"≈Cat A (1-3 providers) — {rc} reviews suggests small practice",
        })
    elif rc < 150:
        breakdown.append({
            "label": "Practice size",
            "score": 12,
            "max": 15,
            "reason": f"≈Cat B (3-5 providers) — {rc} reviews suggests medium practice",
        })
    elif rc < 400:
        breakdown.append({
            "label": "Practice size",
            "score": 5,
            "max": 15,
            "reason": f"≈Cat C (5-10 providers) — {rc} reviews; opportunistic only",
        })
    else:
        breakdown.append({
            "label": "Practice size",
            "score": 10,
            "max": 15,
            "reason": f"≈Cat D (10+ providers) — {rc}+ reviews; enterprise expansion focus",
        })

    # ---------- 4. Rating opportunity (INVERSE — lower = higher score) ----------
    rating_raw = practice.get("rating")
    rating = float(rating_raw) if rating_raw is not None else 5.0
    if rating < 3.0:
        breakdown.append({
            "label": "Rating opportunity",
            "score": 20,
            "max": 20,
            "reason": f"{rating}★ — clear pain, strong opportunity to improve",
        })
    elif rating < 3.5:
        breakdown.append({
            "label": "Rating opportunity",
            "score": 17,
            "max": 20,
            "reason": f"{rating}★ — significant room for improvement",
        })
    elif rating < 4.0:
        breakdown.append({
            "label": "Rating opportunity",
            "score": 13,
            "max": 20,
            "reason": f"{rating}★ — moderate room for improvement",
        })
    elif rating < 4.3:
        breakdown.append({
            "label": "Rating opportunity",
            "score": 9,
            "max": 20,
            "reason": f"{rating}★ — solid but not exceptional",
        })
    elif rating < 4.5:
        breakdown.append({
            "label": "Rating opportunity",
            "score": 5,
            "max": 20,
            "reason": f"{rating}★ — already performing well",
        })
    else:
        breakdown.append({
            "label": "Rating opportunity",
            "score": 2,
            "max": 20,
            "reason": f"{rating}★ — already excelling, limited pain to relieve",
        })

    # ---------- 5. Review depth (data quality signal) ----------
    if rc >= 100:
        breakdown.append({
            "label": "Review depth",
            "score": 10,
            "max": 10,
            "reason": f"{rc} reviews — strong data signal for analysis",
        })
    elif rc >= 50:
        breakdown.append({
            "label": "Review depth",
            "score": 8,
            "max": 10,
            "reason": f"{rc} reviews — solid signal",
        })
    elif rc >= 20:
        breakdown.append({
            "label": "Review depth",
            "score": 6,
            "max": 10,
            "reason": f"{rc} reviews",
        })
    elif rc >= 5:
        breakdown.append({
            "label": "Review depth",
            "score": 4,
            "max": 10,
            "reason": f"{rc} reviews — limited signal",
        })
    else:
        breakdown.append({
            "label": "Review depth",
            "score": 1,
            "max": 10,
            "reason": f"{rc} reviews — insufficient signal",
        })

    # ---------- 6. Website presence ----------
    if practice.get("website"):
        breakdown.append({
            "label": "Website presence",
            "score": 5,
            "max": 5,
            "reason": "Has a website — established practice",
        })
    else:
        breakdown.append({
            "label": "Website presence",
            "score": 0,
            "max": 5,
            "reason": "No website on file",
        })

    # ---------- 7. Hiring signal (from AI) ----------
    hs = int(practice.get("hiring_signal_score") or 0)
    hs_score = round(hs * 15 / 100)
    breakdown.append({
        "label": "Hiring signals",
        "score": hs_score,
        "max": 15,
        "reason": f"AI detected hiring signal: {hs}/100",
    })

    # ---------- 8. Urgency (from AI) ----------
    us = int(practice.get("urgency_score") or 0)
    us_score = round(us * 10 / 100)
    breakdown.append({
        "label": "Urgency",
        "score": us_score,
        "max": 10,
        "reason": f"AI detected urgency: {us}/100",
    })

    total = sum(b["score"] for b in breakdown)
    return {"total": total, "breakdown": breakdown}


_US_STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
})


def _is_us_state(state: str) -> bool:
    return state.upper() in _US_STATES
