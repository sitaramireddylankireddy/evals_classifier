"""Build the evaluation report and write it as Markdown and JSON.

The report holds measures, counts, item IDs, and timings. It never holds text from an item.
"""

from pathlib import Path

from evalsvc.config import GoldenSettings, SweepSettings
from evalsvc.harness.golden import GoldenLoad
from evalsvc.harness.metrics import (
    Comparison,
    Measures,
    SweepPoint,
    Timing,
    by_category,
    compute_measures,
    pick_threshold,
    sweep,
    timing,
)
from evalsvc.harness.scoring import ScoredItem
from evalsvc.types import FrozenModel, ModelInfo

MARKDOWN_NAME = "report.md"
JSON_NAME = "report.json"


class Counts(FrozenModel):
    in_file: int
    malformed: int  # rejected by the input parser
    unlabelled: int  # missing or unknown label
    not_evaluable: int
    evaluated: int
    labelled_failures: int


class ItemScore(FrozenModel):
    item_id: str
    is_failure: bool
    category: str | None
    evaluable: bool
    not_evaluable_reason: str | None
    score: float | None
    predicted_failure: bool | None
    seconds: float | None


class ConfigReport(FrozenModel):
    label: str
    model: ModelInfo
    threshold: float
    counts: Counts
    overall: Measures
    by_category: dict[str, Measures]
    sweep: list[SweepPoint] | None = None
    recall_target: float | None = None
    picked_threshold: float | None = None
    timing: Timing
    items: list[ItemScore]


class Report(FrozenModel):
    run_id: str
    date: str
    golden_file: str
    golden_sha256: str
    configs: list[ConfigReport]
    comparison: Comparison | None = None


def build_config_report(
    label: str,
    model: ModelInfo,
    threshold: float,
    load: GoldenLoad,
    scored: list[ScoredItem],
    golden: GoldenSettings,
    sweep_settings: SweepSettings | None,
) -> ConfigReport:
    overall = compute_measures(scored, threshold, golden.min_group_size)
    points = None
    picked = None
    if sweep_settings is not None:
        points = sweep(scored, sweep_settings, golden.min_group_size)
        picked = pick_threshold(points, sweep_settings.recall_target)

    return ConfigReport(
        label=label,
        model=model,
        threshold=threshold,
        counts=Counts(
            in_file=len(load.items) + load.unlabelled + len(load.issues),
            malformed=len(load.issues),
            unlabelled=load.unlabelled,
            not_evaluable=sum(1 for item in scored if not item.evaluable),
            evaluated=overall.n,
            labelled_failures=overall.failures,
        ),
        overall=overall,
        by_category={
            name: compute_measures(group, threshold, golden.min_group_size)
            for name, group in by_category(scored).items()
        },
        sweep=points,
        recall_target=sweep_settings.recall_target if sweep_settings is not None else None,
        picked_threshold=picked,
        timing=timing(scored),
        items=[
            ItemScore(
                item_id=item.item_id,
                is_failure=item.is_failure,
                category=item.category,
                evaluable=item.evaluable,
                not_evaluable_reason=item.not_evaluable_reason,
                score=item.score,
                predicted_failure=item.score > threshold if item.score is not None else None,
                seconds=item.seconds,
            )
            for item in scored
        ],
    )


_EMPTY_REASONS = {
    "recall": "no labelled failures",
    "precision": "nothing was predicted as a failure",
    "false_alarm_rate": "no labelled passes",
    "pr_auc": "no labelled failures",
}


def _value(measures: Measures, name: str) -> str:
    value = getattr(measures, name)
    return f"{value:.3f}" if value is not None else f"n/a ({_EMPTY_REASONS[name]})"


def _number(value: float | None, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if value is not None else "n/a"


def _measure_row(name: str, m: Measures) -> str:
    note = "" if m.reliable else " (unreliable: too few items)"
    return (
        f"| {name} | {m.n}{note} | {m.failures} | {_number(m.recall)} | {_number(m.precision)} "
        f"| {_number(m.false_alarm_rate)} | {_number(m.pr_auc)} |"
    )


def _config_lines(config: ConfigReport) -> list[str]:
    m, c = config.overall, config.counts
    lines = [
        f"## {config.label}",
        "",
        f"Model: {config.model.name}, revision {config.model.revision}, "
        f"device {config.model.device}. Threshold: {config.threshold}.",
        "",
        f"- **Recall on known failures: {_value(m, 'recall')}** "
        f"({m.tp} of {m.failures} labelled failures were flagged)",
        f"- Precision: {_value(m, 'precision')}",
        f"- False-alarm rate: {_value(m, 'false_alarm_rate')}",
        f"- Area under the precision-recall curve: {_value(m, 'pr_auc')}",
        "",
        f"Items in file: {c.in_file}. Evaluated: {c.evaluated}. Not evaluable: {c.not_evaluable}. "
        f"Unlabelled: {c.unlabelled}. Malformed: {c.malformed}. "
        f"Labelled failures: {c.labelled_failures}.",
        "",
        f"Flagged correctly: {m.tp}. False alarms: {m.fp}. Missed failures: {m.fn}. "
        f"Passed correctly: {m.tn}.",
    ]
    if not m.reliable:
        lines += ["", "These figures are unreliable: too few items were evaluated."]
    lines += [
        "",
        f"Detection time per item: mean {_number(config.timing.mean_seconds)} s, "
        f"95th percentile {_number(config.timing.p95_seconds)} s.",
    ]

    if config.by_category:
        lines += [
            "",
            "### By category",
            "",
            "| Category | Items | Failures | Recall | Precision | False-alarm rate | PR AUC |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [_measure_row(name, measures) for name, measures in config.by_category.items()]

    if config.sweep is not None:
        lines += [
            "",
            "### Threshold sweep",
            "",
            "| Threshold | Recall | Precision | False-alarm rate |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {point.threshold:.2f} | {_number(point.measures.recall)} "
            f"| {_number(point.measures.precision)} "
            f"| {_number(point.measures.false_alarm_rate)} |"
            for point in config.sweep
        ]
        if config.picked_threshold is not None:
            chosen = next(p for p in config.sweep if p.threshold == config.picked_threshold)
            lines += [
                "",
                f"Highest threshold with recall of at least {config.recall_target}: "
                f"**{config.picked_threshold:.2f}** "
                f"(precision {_number(chosen.measures.precision)}).",
            ]
        else:
            lines += ["", f"No threshold reaches a recall of {config.recall_target}."]
    return lines


def _comparison_lines(comparison: Comparison) -> list[str]:
    a, b = comparison.measures_a, comparison.measures_b
    names = {
        "recall": "Recall on known failures",
        "precision": "Precision",
        "false_alarm_rate": "False-alarm rate",
        "pr_auc": "PR AUC",
    }
    lines = [
        f"## Comparison: {comparison.label_a} and {comparison.label_b}",
        "",
        f"| Measure | {comparison.label_a} | {comparison.label_b} | Difference |",
        "|---|---|---|---|",
    ]
    for key, title in names.items():
        difference = comparison.differences[key]
        shown = f"{difference:+.3f}" if difference is not None else "n/a"
        lines.append(
            f"| {title} | {_number(getattr(a, key))} | {_number(getattr(b, key))} | {shown} |"
        )
    lines += [
        f"| Mean seconds per item | {_number(comparison.timing_a.mean_seconds)} "
        f"| {_number(comparison.timing_b.mean_seconds)} | |",
        f"| 95th percentile seconds | {_number(comparison.timing_a.p95_seconds)} "
        f"| {_number(comparison.timing_b.p95_seconds)} | |",
        "",
        f"Items where the two verdicts differ: {len(comparison.disagreements)}.",
    ]
    if comparison.disagreements:
        lines += ["", ", ".join(comparison.disagreements)]
    return lines


def render_markdown(report: Report) -> str:
    lines = [
        "# Groundedness evaluation report",
        "",
        f"Run {report.run_id} on {report.date}.",
        f"Golden set: {report.golden_file} (SHA-256 {report.golden_sha256}).",
    ]
    for config in report.configs:
        lines += ["", *_config_lines(config)]
    if report.comparison is not None:
        lines += ["", *_comparison_lines(report.comparison)]
    return "\n".join(lines) + "\n"


def write_report(report: Report, out_dir: Path) -> Path:
    """Write report.md and report.json into a folder named after the run. Returns the folder."""
    folder = out_dir / report.run_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MARKDOWN_NAME).write_text(render_markdown(report), encoding="utf-8")
    (folder / JSON_NAME).write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return folder
