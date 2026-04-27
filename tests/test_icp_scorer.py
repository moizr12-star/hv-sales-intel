from src.icp_scorer import score_icp


def test_perfect_florida_psychiatry_struggling_practice():
    """A small Florida psych practice with low rating should score very high."""
    p = {
        "state": "FL",
        "category": "mental_health",
        "review_count": 30,
        "rating": 2.8,
        "website": "https://example.com",
        "hiring_signal_score": 90,
        "urgency_score": 80,
    }
    result = score_icp(p)
    # 10 + 15 + 15 + 20 + 6 + 5 + 14 + 8 = 93
    assert result["total"] >= 90
    by_label = {b["label"]: b for b in result["breakdown"]}
    assert by_label["Geography"]["score"] == 10
    assert by_label["Specialty fit"]["score"] == 15
    assert by_label["Rating opportunity"]["score"] == 20


def test_high_rating_excellent_practice_scores_low_on_opportunity():
    """A 4.9★ practice has low opportunity even if other signals are strong."""
    p = {
        "state": "FL",
        "category": "mental_health",
        "review_count": 200,
        "rating": 4.9,
        "website": "https://example.com",
        "hiring_signal_score": 50,
        "urgency_score": 30,
    }
    result = score_icp(p)
    by_label = {b["label"]: b for b in result["breakdown"]}
    assert by_label["Rating opportunity"]["score"] == 2  # the lowest bucket


def test_outside_us_zero_geography():
    p = {
        "state": "NSW",
        "category": "mental_health",
        "review_count": 30,
        "rating": 3.5,
        "website": None,
        "hiring_signal_score": 0,
        "urgency_score": 0,
    }
    result = score_icp(p)
    by_label = {b["label"]: b for b in result["breakdown"]}
    assert by_label["Geography"]["score"] == 0


def test_us_non_florida_gets_partial_geography():
    p = {
        "state": "TX",
        "category": "primary_care",
        "review_count": 30,
        "rating": 3.5,
        "website": "https://x.com",
        "hiring_signal_score": 0,
        "urgency_score": 0,
    }
    result = score_icp(p)
    by_label = {b["label"]: b for b in result["breakdown"]}
    assert by_label["Geography"]["score"] == 5


def test_review_count_buckets_practice_size_correctly():
    base = {
        "state": "FL",
        "category": "primary_care",
        "rating": 3.5,
        "website": None,
        "hiring_signal_score": 0,
        "urgency_score": 0,
    }
    sizes = {10: 15, 80: 12, 250: 5, 600: 10}
    for rc, expected_score in sizes.items():
        result = score_icp({**base, "review_count": rc})
        by_label = {b["label"]: b for b in result["breakdown"]}
        assert by_label["Practice size"]["score"] == expected_score, (
            f"review_count={rc} expected {expected_score}, got "
            f"{by_label['Practice size']['score']}"
        )


def test_low_review_count_means_low_data_signal():
    p = {
        "state": "FL",
        "category": "primary_care",
        "review_count": 2,
        "rating": 3.5,
        "website": "https://x.com",
        "hiring_signal_score": 50,
        "urgency_score": 50,
    }
    result = score_icp(p)
    by_label = {b["label"]: b for b in result["breakdown"]}
    assert by_label["Review depth"]["score"] == 1


def test_total_caps_at_100():
    """Even with maxed-out signals, total should be ≤ 100."""
    p = {
        "state": "FL",
        "category": "mental_health",
        "review_count": 80,
        "rating": 1.0,
        "website": "https://x.com",
        "hiring_signal_score": 100,
        "urgency_score": 100,
    }
    result = score_icp(p)
    assert result["total"] <= 100
    # 10 + 15 + 12 + 20 + 8 + 5 + 15 + 10 = 95 — verify near-max
    assert result["total"] >= 90


def test_breakdown_includes_all_eight_dimensions():
    p = {
        "state": "FL",
        "category": "mental_health",
        "review_count": 30,
        "rating": 3.5,
        "website": "https://x.com",
        "hiring_signal_score": 50,
        "urgency_score": 50,
    }
    result = score_icp(p)
    labels = [b["label"] for b in result["breakdown"]]
    assert labels == [
        "Geography",
        "Specialty fit",
        "Practice size",
        "Rating opportunity",
        "Review depth",
        "Website presence",
        "Hiring signals",
        "Urgency",
    ]


def test_each_breakdown_row_has_required_fields():
    p = {
        "state": "FL", "category": "mental_health", "review_count": 30,
        "rating": 3.5, "website": "https://x.com",
        "hiring_signal_score": 50, "urgency_score": 50,
    }
    result = score_icp(p)
    for row in result["breakdown"]:
        assert set(row.keys()) == {"label", "score", "max", "reason"}
        assert 0 <= row["score"] <= row["max"]
        assert isinstance(row["reason"], str) and row["reason"]
