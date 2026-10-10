"""Quality measures for the detector against golden labels.

"Failure" is the positive class: an item whose answer has unsupported content.
An item is predicted as a failure at threshold t when its score is above t.
A measure that cannot be computed is None, never zero.
"""

import math

from evalsvc.config import SweepSettings
from evalsvc.harness.scoring import ScoredItem
from evalsvc.types import FrozenModel


class Measures(FrozenModel):
    n: int  # evaluated items
    failures: int  # labelled failures among them
    tp: int
    fp: int
    tn: int
    fn: int
    recall: float | None  # None when there are no labelled failures
    precision: float | None  # None when nothing was predicted as a failure
    false_alarm_rate: float | None  # None when there are no labelled passes
    pr_auc: float | None  # None when there are no labelled failures
    reliable: bool  # False when n is below the minimum group size


class SweepPoint(FrozenModel):
    threshold: float
    measures: Measures


class Timing(FrozenModel):
    mean_seconds: float | None
    p95_seconds: float | None


class Comparison(FrozenModel):
    label_a: str
    label_b: str
    measures_a: Measures
    measures_b: Measures
    differences: dict[str, float | None]  # b minus a, for each measure
    disagreements: list[str]  # IDs of items where the two verdicts differ
    timing_a: Timing
    timing_b: Timing


def _evaluated(scored: list[ScoredItem]) -> list[ScoredItem]:
    return [item for item in scored if item.evaluable and item.score is not None]


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def average_precision(labels: list[bool], scores: list[float]) -> float | None:
    """Area under the precision-recall curve.

    Items with the same score are taken together, so the result does not
    depend on their order.
    """
    total_failures = sum(labels)
    if total_failures == 0:
        return None

    by_score: dict[float, list[bool]] = {}
    for label, score in zip(labels, scores):
        by_score.setdefault(score, []).append(label)

    area = 0.0
    true_positives = 0
    predicted = 0
    previous_recall = 0.0
    for score in sorted(by_score, reverse=True):
        group = by_score[score]
        true_positives += sum(group)
        predicted += len(group)
        recall = true_positives / total_failures
        area += (recall - previous_recall) * (true_positives / predicted)
        previous_recall = recall
    return area


def compute_measures(scored: list[ScoredItem], threshold: float, min_group: int) -> Measures:
    items = _evaluated(scored)
    tp = sum(1 for item in items if item.is_failure and item.score > threshold)
    fn = sum(1 for item in items if item.is_failure and item.score <= threshold)
    fp = sum(1 for item in items if not item.is_failure and item.score > threshold)
    tn = sum(1 for item in items if not item.is_failure and item.score <= threshold)
    return Measures(
        n=len(items),
        failures=tp + fn,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        recall=_ratio(tp, tp + fn),
        precision=_ratio(tp, tp + fp),
        false_alarm_rate=_ratio(fp, fp + tn),
        pr_auc=average_precision(
            [item.is_failure for item in items], [item.score for item in items]
        ),
        reliable=len(items) >= min_group,
    )


def by_category(scored: list[ScoredItem]) -> dict[str, list[ScoredItem]]:
    """Items grouped by category, in sorted order. Items with no category are left out."""
    groups: dict[str, list[ScoredItem]] = {}
    for item in scored:
        if item.category is not None:
            groups.setdefault(item.category, []).append(item)
    return dict(sorted(groups.items()))


def sweep_thresholds(settings: SweepSettings) -> list[float]:
    steps = round((settings.stop - settings.start) / settings.step)
    return [round(settings.start + i * settings.step, 6) for i in range(steps + 1)]


def sweep(scored: list[ScoredItem], settings: SweepSettings, min_group: int) -> list[SweepPoint]:
    """The measures at each threshold in the configured range. No detector call is made."""
    return [
        SweepPoint(threshold=threshold, measures=compute_measures(scored, threshold, min_group))
        for threshold in sweep_thresholds(settings)
    ]


def pick_threshold(points: list[SweepPoint], recall_target: float) -> float | None:
    """The highest threshold whose recall meets the target, or None when none does."""
    meeting = [
        point.threshold
        for point in points
        if point.measures.recall is not None and point.measures.recall >= recall_target
    ]
    return max(meeting, default=None)


def timing(scored: list[ScoredItem]) -> Timing:
    seconds = sorted(item.seconds for item in scored if item.seconds is not None)
    if not seconds:
        return Timing(mean_seconds=None, p95_seconds=None)
    return Timing(
        mean_seconds=sum(seconds) / len(seconds),
        p95_seconds=seconds[math.ceil(0.95 * len(seconds)) - 1],
    )


_COMPARED = ("recall", "precision", "false_alarm_rate", "pr_auc")


def compare(
    label_a: str,
    scored_a: list[ScoredItem],
    threshold_a: float,
    label_b: str,
    scored_b: list[ScoredItem],
    threshold_b: float,
    min_group: int,
) -> Comparison:
    measures_a = compute_measures(scored_a, threshold_a, min_group)
    measures_b = compute_measures(scored_b, threshold_b, min_group)

    differences: dict[str, float | None] = {}
    for name in _COMPARED:
        value_a, value_b = getattr(measures_a, name), getattr(measures_b, name)
        differences[name] = None if value_a is None or value_b is None else value_b - value_a

    verdicts_a = {item.item_id: item.score > threshold_a for item in _evaluated(scored_a)}
    verdicts_b = {item.item_id: item.score > threshold_b for item in _evaluated(scored_b)}
    disagreements = [
        item_id
        for item_id, verdict in verdicts_a.items()
        if item_id in verdicts_b and verdicts_b[item_id] != verdict
    ]

    return Comparison(
        label_a=label_a,
        label_b=label_b,
        measures_a=measures_a,
        measures_b=measures_b,
        differences=differences,
        disagreements=disagreements,
        timing_a=timing(scored_a),
        timing_b=timing(scored_b),
    )
