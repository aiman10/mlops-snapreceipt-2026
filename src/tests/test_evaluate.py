from pipelines.evaluate import field_score


def test_perfect_match_scores_one():
    pred = {"total_amount": 11.45, "items": [{"description": "A"}, {"description": "B"}]}
    gt = {"total": "11.45", "items": [{"description": "A"}, {"description": "B"}]}
    assert field_score(pred, gt) == 1.0


def test_total_mismatch_lowers_score():
    pred = {"total_amount": 9.99, "items": []}
    gt = {"total": "11.45", "items": []}
    assert field_score(pred, gt) < 1.0


def test_item_count_within_tolerance_counts_as_match():
    pred = {"total_amount": 5.0, "items": [{"description": "A"}, {"description": "B"}]}
    gt = {"total": "5.00", "items": [{"description": "A"}, {"description": "B"}, {"description": "C"}]}
    # total matches; item count off by 1 (tolerated) -> full score
    assert field_score(pred, gt) == 1.0
