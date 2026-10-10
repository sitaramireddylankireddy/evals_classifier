import json

from evalsvc.config import GoldenSettings, SweepSettings
from evalsvc.harness.golden import GoldenItem, GoldenLoad
from evalsvc.harness.metrics import compare
from evalsvc.harness.report import (
    JSON_NAME,
    MARKDOWN_NAME,
    Report,
    build_config_report,
    render_markdown,
    write_report,
)
from evalsvc.harness.scoring import ScoredItem
from evalsvc.types import IngestIssue, ModelInfo, ReasonCode
from tests.fakes import make_item

MODEL = ModelInfo(name="fake-detector", revision="rev-1", device="cpu")
GOLDEN = GoldenSettings(min_group_size=2)


def scored(item_id, is_failure, score, category=None):
    return ScoredItem(
        item_id=item_id,
        is_failure=is_failure,
        category=category,
        evaluable=True,
        score=score,
        seconds=0.2,
    )


SCORED = [
    scored("f1", True, 0.9, "cards"),
    scored("f2", True, 0.3, "cards"),
    scored("p1", False, 0.7, "loans"),
    scored("p2", False, 0.1, "loans"),
    ScoredItem(item_id="x1", is_failure=True, evaluable=False, not_evaluable_reason="empty_answer"),
]


def make_load(sentinel="text"):
    items = [
        GoldenItem(item=make_item(s.item_id, answer=f"Alpha {sentinel}."), is_failure=s.is_failure)
        for s in SCORED
    ]
    issues = [IngestIssue(position=7, reason=ReasonCode.NOT_AN_OBJECT)]
    return GoldenLoad(items=items, issues=issues, unlabelled=2)


def config_report(label="config", sweep_settings=None, sentinel="text"):
    return build_config_report(label, MODEL, 0.5, make_load(sentinel), SCORED, GOLDEN, sweep_settings)


def make_report(**kwargs):
    return Report(
        run_id="20261010T120000-abcd1234",
        date="2026-10-10T12:00:00+00:00",
        golden_file="golden.jsonl",
        golden_sha256="0" * 64,
        **kwargs,
    )


def test_config_report_holds_counts_and_measures():
    report = config_report()

    assert report.counts.in_file == 8  # 5 labelled + 2 unlabelled + 1 malformed
    assert report.counts.malformed == 1
    assert report.counts.unlabelled == 2
    assert report.counts.not_evaluable == 1
    assert report.counts.evaluated == 4
    assert report.counts.labelled_failures == 2
    assert (report.overall.tp, report.overall.fp, report.overall.tn, report.overall.fn) == (1, 1, 1, 1)
    assert list(report.by_category) == ["cards", "loans"]
    assert report.sweep is None
    assert report.picked_threshold is None
    assert report.threshold == 0.5
    assert report.model == MODEL


def test_items_carry_their_score_and_prediction_but_no_text():
    report = config_report()

    by_id = {item.item_id: item for item in report.items}
    assert (by_id["f1"].score, by_id["f1"].predicted_failure) == (0.9, True)
    assert (by_id["f2"].score, by_id["f2"].predicted_failure) == (0.3, False)
    assert (by_id["x1"].score, by_id["x1"].predicted_failure) == (None, None)
    assert by_id["x1"].not_evaluable_reason == "empty_answer"


def test_sweep_is_added_when_asked_for():
    report = config_report(sweep_settings=SweepSettings(recall_target=0.5))

    assert len(report.sweep) == 19
    assert report.recall_target == 0.5
    # One of the two failures scores 0.9, so recall is 0.5 up to a threshold of 0.85.
    assert report.picked_threshold == 0.85


def test_markdown_puts_recall_on_known_failures_first():
    text = render_markdown(make_report(configs=[config_report()]))

    recall = text.index("Recall on known failures")
    assert recall < text.index("Precision")
    assert recall < text.index("False-alarm rate")
    assert "Recall on known failures: 0.500" in text
    assert "(1 of 2 labelled failures were flagged)" in text
    assert "Evaluated: 4. Not evaluable: 1. Unlabelled: 2. Malformed: 1. Labelled failures: 2." in text
    assert "fake-detector, revision rev-1, device cpu. Threshold: 0.5." in text
    assert "golden.jsonl (SHA-256 " + "0" * 64 + ")" in text
    assert "### By category" in text
    assert "Threshold sweep" not in text


def test_markdown_states_why_a_measure_is_empty():
    only_passes = [scored("p1", False, 0.1), scored("p2", False, 0.2)]
    load = GoldenLoad(items=[], issues=[], unlabelled=0)
    report = build_config_report("config", MODEL, 0.5, load, only_passes, GOLDEN, None)

    text = render_markdown(make_report(configs=[report]))

    assert "Recall on known failures: n/a (no labelled failures)" in text
    assert "Precision: n/a (nothing was predicted as a failure)" in text


def test_markdown_marks_small_groups_as_unreliable():
    report = build_config_report(
        "config", MODEL, 0.5, make_load(), SCORED, GoldenSettings(min_group_size=50), None
    )

    text = render_markdown(make_report(configs=[report]))

    assert "These figures are unreliable: too few items were evaluated." in text
    assert "(unreliable: too few items)" in text


def test_markdown_shows_the_sweep_and_the_picked_threshold():
    report = config_report(sweep_settings=SweepSettings(recall_target=0.5))

    text = render_markdown(make_report(configs=[report]))

    assert "### Threshold sweep" in text
    assert "Highest threshold with recall of at least 0.5: **0.85**" in text


def test_markdown_shows_the_comparison():
    other = [scored("f1", True, 0.9), scored("f2", True, 0.8), scored("p1", False, 0.1), scored("p2", False, 0.1)]
    comparison = compare("large", SCORED, 0.5, "base", other, 0.5, min_group=2)
    report = make_report(
        configs=[config_report("large"), config_report("base")], comparison=comparison
    )

    text = render_markdown(report)

    assert "## Comparison: large and base" in text
    assert "| Recall on known failures | 0.500 | 1.000 | +0.500 |" in text
    assert "Items where the two verdicts differ: 2." in text
    assert "f2, p1" in text


def test_report_files_are_written_and_json_loads_back(tmp_path):
    report = make_report(configs=[config_report(sweep_settings=SweepSettings())])

    folder = write_report(report, tmp_path / "reports")

    assert folder == tmp_path / "reports" / "20261010T120000-abcd1234"
    assert (folder / MARKDOWN_NAME).read_text(encoding="utf-8") == render_markdown(report)
    loaded = json.loads((folder / JSON_NAME).read_text(encoding="utf-8"))
    assert loaded["golden_sha256"] == "0" * 64
    assert loaded["configs"][0]["overall"]["recall"] == 0.5
    assert loaded["configs"][0]["model"] == {"name": "fake-detector", "revision": "rev-1", "device": "cpu"}
    assert Report.model_validate(loaded) == report


def test_report_files_hold_no_text_from_the_items(tmp_path, sentinel):
    report = make_report(configs=[config_report(sentinel=sentinel)])

    folder = write_report(report, tmp_path / "reports")

    assert sentinel not in (folder / MARKDOWN_NAME).read_text(encoding="utf-8")
    assert sentinel not in (folder / JSON_NAME).read_text(encoding="utf-8")
