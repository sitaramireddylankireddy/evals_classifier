import pytest

from evalsvc.config import SweepSettings
from evalsvc.harness.metrics import (
    average_precision,
    by_category,
    compare,
    compute_measures,
    pick_threshold,
    sweep,
    sweep_thresholds,
    timing,
)
from evalsvc.harness.scoring import ScoredItem


def scored(item_id, is_failure, score, category=None, seconds=0.1):
    return ScoredItem(
        item_id=item_id,
        is_failure=is_failure,
        category=category,
        evaluable=True,
        score=score,
        seconds=seconds,
    )


def not_evaluable(item_id, is_failure=True):
    return ScoredItem(
        item_id=item_id, is_failure=is_failure, evaluable=False, not_evaluable_reason="empty_answer"
    )


# Failures score 0.9, 0.8, 0.3. Passes score 0.7, 0.2, 0.1.
ITEMS = [
    scored("f1", True, 0.9, "cards"),
    scored("f2", True, 0.8, "cards"),
    scored("f3", True, 0.3, "loans"),
    scored("p1", False, 0.7, "cards"),
    scored("p2", False, 0.2, "loans"),
    scored("p3", False, 0.1, "loans"),
]


# --- Counts and rates (T004) ---


def test_counts_and_rates_at_one_threshold():
    m = compute_measures(ITEMS, 0.5, min_group=1)

    assert (m.n, m.failures) == (6, 3)
    assert (m.tp, m.fp, m.tn, m.fn) == (2, 1, 2, 1)
    assert m.recall == pytest.approx(2 / 3)
    assert m.precision == pytest.approx(2 / 3)
    assert m.false_alarm_rate == pytest.approx(1 / 3)
    assert m.reliable is True


def test_score_equal_to_the_threshold_is_not_a_predicted_failure():
    m = compute_measures([scored("f1", True, 0.5), scored("p1", False, 0.5)], 0.5, min_group=1)

    assert (m.tp, m.fp, m.tn, m.fn) == (0, 0, 1, 1)


def test_no_labelled_failures_gives_empty_recall():
    m = compute_measures([scored("p1", False, 0.9), scored("p2", False, 0.1)], 0.5, min_group=1)

    assert m.recall is None
    assert m.pr_auc is None
    assert m.precision == 0.0
    assert m.false_alarm_rate == 0.5


def test_no_predicted_failures_gives_empty_precision():
    m = compute_measures([scored("f1", True, 0.2), scored("p1", False, 0.1)], 0.5, min_group=1)

    assert m.precision is None
    assert m.recall == 0.0


def test_no_labelled_passes_gives_an_empty_false_alarm_rate():
    m = compute_measures([scored("f1", True, 0.9)], 0.5, min_group=1)

    assert m.false_alarm_rate is None
    assert m.recall == 1.0


def test_items_that_are_not_evaluable_are_left_out():
    m = compute_measures(ITEMS + [not_evaluable("x1"), not_evaluable("x2")], 0.5, min_group=1)

    assert (m.n, m.failures) == (6, 3)


def test_group_below_the_minimum_size_is_unreliable():
    assert compute_measures(ITEMS, 0.5, min_group=7).reliable is False
    assert compute_measures(ITEMS, 0.5, min_group=6).reliable is True


def test_no_items_at_all():
    m = compute_measures([], 0.5, min_group=1)

    assert (m.n, m.recall, m.precision, m.false_alarm_rate, m.pr_auc) == (0, None, None, None, None)


# --- Area under the precision-recall curve (T005) ---


def test_perfect_ranking_gives_one():
    assert average_precision([True, True, False, False], [0.9, 0.8, 0.2, 0.1]) == 1.0


def test_hand_worked_five_item_case():
    # Failures are ranked 1st, 3rd, and 5th: (1/1 + 2/3 + 3/5) / 3 = 34/45.
    labels = [True, False, True, False, True]
    scores = [0.9, 0.8, 0.7, 0.6, 0.5]

    assert average_precision(labels, scores) == pytest.approx(34 / 45)


def test_tied_scores_give_the_same_result_in_any_order():
    # At 0.9: recall 1/2, precision 1. At 0.5: recall 1, precision 2/3. Area = 1/2 + 1/3.
    expected = 1 / 2 + 1 / 3

    assert average_precision([True, True, False], [0.9, 0.5, 0.5]) == pytest.approx(expected)
    assert average_precision([True, False, True], [0.9, 0.5, 0.5]) == pytest.approx(expected)


def test_no_failures_gives_no_area_and_only_failures_gives_one():
    assert average_precision([False, False], [0.9, 0.1]) is None
    assert average_precision([], []) is None
    assert average_precision([True, True], [0.9, 0.1]) == 1.0


def test_measures_carry_the_area():
    # Ranking: f1, f2, p1, f3, p2, p3. Area = (1 + 1 + 3/4) / 3.
    m = compute_measures(ITEMS, 0.5, min_group=1)

    assert m.pr_auc == pytest.approx((1 + 1 + 3 / 4) / 3)


# --- Threshold sweep (T007) ---


def test_sweep_has_one_point_per_threshold():
    points = sweep(ITEMS, SweepSettings(), min_group=1)

    assert [point.threshold for point in points] == sweep_thresholds(SweepSettings())
    assert len(points) == 19
    assert points[0].threshold == 0.05
    assert points[-1].threshold == 0.95


def test_recall_never_rises_as_the_threshold_rises():
    recalls = [point.measures.recall for point in sweep(ITEMS, SweepSettings(), min_group=1)]

    assert all(earlier >= later for earlier, later in zip(recalls, recalls[1:]))
    assert recalls[0] == 1.0
    assert recalls[-1] == 0.0


def test_pick_threshold_returns_the_highest_that_meets_the_target():
    points = sweep(ITEMS, SweepSettings(), min_group=1)

    # The lowest-scoring failure is at 0.3, so recall is 1.0 only below 0.3.
    assert pick_threshold(points, 0.9) == 0.25
    # Two of three failures score 0.8 or more.
    assert pick_threshold(points, 0.6) == 0.75
    assert pick_threshold(points, 0.0) == 0.95


def test_pick_threshold_returns_nothing_when_no_threshold_meets_the_target():
    items = [scored("f1", True, 0.9), scored("f2", True, 0.01), scored("p1", False, 0.2)]

    points = sweep(items, SweepSettings(), min_group=1)

    assert pick_threshold(points, 1.0) is None


def test_custom_sweep_range():
    settings = SweepSettings(start=0.2, stop=0.8, step=0.2)

    assert sweep_thresholds(settings) == [0.2, 0.4, 0.6, 0.8]


# --- Categories (T008) ---


def test_measures_per_category():
    groups = by_category(ITEMS)

    assert list(groups) == ["cards", "loans"]
    cards = compute_measures(groups["cards"], 0.5, min_group=1)
    loans = compute_measures(groups["loans"], 0.5, min_group=1)
    assert (cards.tp, cards.fp, cards.tn, cards.fn) == (2, 1, 0, 0)
    assert (loans.tp, loans.fp, loans.tn, loans.fn) == (0, 0, 2, 1)
    assert loans.recall == 0.0
    assert loans.precision is None


def test_small_category_is_marked_unreliable():
    groups = by_category(ITEMS)

    assert compute_measures(groups["cards"], 0.5, min_group=20).reliable is False


def test_items_with_no_category_form_no_group():
    assert by_category([scored("f1", True, 0.9), scored("p1", False, 0.1)]) == {}


# --- Comparison and timing (T009) ---


def test_comparison_lists_differences_and_disagreements():
    other = [
        scored("f1", True, 0.9, seconds=0.4),
        scored("f2", True, 0.2, seconds=0.4),  # now missed
        scored("f3", True, 0.6, seconds=0.4),  # now flagged
        scored("p1", False, 0.1, seconds=0.4),  # no longer a false alarm
        scored("p2", False, 0.2, seconds=0.4),
        scored("p3", False, 0.1, seconds=0.4),
    ]

    comparison = compare("large", ITEMS, 0.5, "base", other, 0.5, min_group=1)

    assert (comparison.label_a, comparison.label_b) == ("large", "base")
    assert comparison.disagreements == ["f2", "f3", "p1"]
    assert comparison.measures_a.recall == pytest.approx(2 / 3)
    assert comparison.measures_b.recall == pytest.approx(2 / 3)
    assert comparison.differences["recall"] == pytest.approx(0.0)
    assert comparison.differences["precision"] == pytest.approx(1 - 2 / 3)
    assert comparison.differences["false_alarm_rate"] == pytest.approx(-1 / 3)
    assert comparison.timing_a.mean_seconds == pytest.approx(0.1)
    assert comparison.timing_b.mean_seconds == pytest.approx(0.4)


def test_each_side_uses_its_own_threshold():
    comparison = compare("a", ITEMS, 0.5, "b", ITEMS, 0.75, min_group=1)

    # At 0.75, p1 (0.7) is no longer flagged; nothing else changes.
    assert comparison.disagreements == ["p1"]


def test_difference_is_empty_when_a_measure_is_empty():
    no_failures = [scored("p1", False, 0.1)]

    comparison = compare("a", ITEMS, 0.5, "b", no_failures, 0.5, min_group=1)

    assert comparison.differences["recall"] is None


def test_timing_mean_and_95th_percentile():
    items = [scored(f"i{n}", False, 0.1, seconds=float(n)) for n in range(1, 21)]

    result = timing(items)

    assert result.mean_seconds == pytest.approx(10.5)
    assert result.p95_seconds == 19.0


def test_timing_with_nothing_timed():
    result = timing([not_evaluable("x1")])

    assert (result.mean_seconds, result.p95_seconds) == (None, None)
