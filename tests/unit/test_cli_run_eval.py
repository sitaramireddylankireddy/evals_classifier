import json
import logging

import pytest

from evalsvc.cli.run_eval import EXIT_BAD_INPUT, EXIT_OK, NoStore, main
from evalsvc.pipeline import build_components
from tests.fakes import BlindDetector, FakeDetector

# The hand-worked values are explained in tests/fixtures/golden_expected.md.


def fake_components(settings):
    """The base model is played by a detector that flags nothing; anything else flags as usual."""
    detector = BlindDetector() if settings.model.select == "base" else FakeDetector()
    return build_components(settings, detector=detector, store=NoStore())


def write_config(tmp_path, name="config.toml", extra=""):
    path = tmp_path / name
    store = (tmp_path / "store").as_posix()
    path.write_text(
        f'[golden]\nmin_group_size = 3\n[sweep]\nrecall_target = 0.8\n[store]\npath = "{store}"\n'
        + extra,
        encoding="utf-8",
    )
    return path


def run(tmp_path, fixtures_dir, *flags, factory=fake_components):
    argv = [
        "--config",
        str(write_config(tmp_path)),
        "--golden",
        str(fixtures_dir / "golden_synthetic.jsonl"),
        "--out",
        str(tmp_path / "reports"),
        *flags,
    ]
    return main(argv, components_factory=factory)


def report_folder(tmp_path):
    [folder] = (tmp_path / "reports").iterdir()
    return folder


def load_report(tmp_path):
    return json.loads((report_folder(tmp_path) / "report.json").read_text(encoding="utf-8"))


# --- The command (T011) ---


def test_both_report_files_are_written(tmp_path, fixtures_dir, capsys):
    code = run(tmp_path, fixtures_dir)

    assert code == EXIT_OK
    folder = report_folder(tmp_path)
    assert (folder / "report.md").is_file()
    assert (folder / "report.json").is_file()
    out = capsys.readouterr().out
    assert "recall on known failures 0.800" in out
    assert "Report written to:" in out


def test_nothing_is_written_to_the_result_store(tmp_path, fixtures_dir):
    run(tmp_path, fixtures_dir)

    assert not (tmp_path / "store").exists()


def test_sweep_flag_adds_the_sweep(tmp_path, fixtures_dir):
    run(tmp_path, fixtures_dir, "--sweep")

    config = load_report(tmp_path)["configs"][0]
    assert len(config["sweep"]) == 19
    assert config["recall_target"] == 0.8
    # Scores are 0.05 or 0.95, so recall stays at 0.8 up to a threshold of 0.90.
    assert config["picked_threshold"] == 0.9
    assert [point["measures"]["recall"] for point in config["sweep"]] == [0.8] * 18 + [0.0]
    assert "### Threshold sweep" in (report_folder(tmp_path) / "report.md").read_text(encoding="utf-8")


def test_without_the_sweep_flag_there_is_no_sweep(tmp_path, fixtures_dir):
    run(tmp_path, fixtures_dir)

    assert load_report(tmp_path)["configs"][0]["sweep"] is None


def test_compare_models_runs_both_and_adds_the_comparison(tmp_path, fixtures_dir):
    code = run(tmp_path, fixtures_dir, "--compare-models", "--sweep")

    report = load_report(tmp_path)
    assert code == EXIT_OK
    assert [config["label"] for config in report["configs"]] == ["large", "base"]
    assert [config["model"]["name"] for config in report["configs"]] == [
        "fake-detector",
        "blind-detector",
    ]
    # The sweep is reported for each model.
    assert all(len(config["sweep"]) == 19 for config in report["configs"])
    comparison = report["comparison"]
    assert (comparison["label_a"], comparison["label_b"]) == ("large", "base")
    # The second detector flags nothing, so the two differ on every item the first one flags.
    assert comparison["disagreements"] == ["g-05", "g-06", "g-07", "g-08", "g-10"]
    assert comparison["differences"]["recall"] == pytest.approx(-0.8)
    assert comparison["timing_a"]["mean_seconds"] is not None
    assert comparison["timing_b"]["mean_seconds"] is not None


def test_compare_with_another_config_file(tmp_path, fixtures_dir):
    other = write_config(tmp_path, "other.toml", extra='[model]\nselect = "base"\n')

    code = run(tmp_path, fixtures_dir, "--compare", str(other))

    report = load_report(tmp_path)
    assert code == EXIT_OK
    assert [config["label"] for config in report["configs"]] == ["config", "other"]
    assert report["comparison"]["disagreements"] == ["g-05", "g-06", "g-07", "g-08", "g-10"]


def test_model_flag_forces_the_model(tmp_path, fixtures_dir):
    seen = []

    def factory(settings):
        seen.append(settings.model.select)
        return fake_components(settings)

    run(tmp_path, fixtures_dir, "--model", "base", factory=factory)

    report = load_report(tmp_path)
    assert seen == ["base"]
    assert report["configs"][0]["label"] == "base"
    assert report["configs"][0]["model"]["name"] == "blind-detector"
    assert report["comparison"] is None


def test_model_flag_cannot_be_combined_with_compare_models(tmp_path, fixtures_dir):
    with pytest.raises(SystemExit):
        run(tmp_path, fixtures_dir, "--model", "base", "--compare-models")


def test_missing_golden_file_exits_with_bad_input(tmp_path, capsys):
    argv = [
        "--config",
        str(write_config(tmp_path)),
        "--golden",
        str(tmp_path / "absent.jsonl"),
        "--out",
        str(tmp_path / "reports"),
    ]

    code = main(argv, components_factory=fake_components)

    assert code == EXIT_BAD_INPUT
    assert "Cannot read input file" in capsys.readouterr().err


def test_model_that_is_not_configured_exits_with_bad_input(tmp_path, fixtures_dir, capsys, monkeypatch):
    from evalsvc import pipeline

    monkeypatch.setattr(pipeline, "gpu_available", lambda: False)
    argv = [
        "--config",
        str(write_config(tmp_path)),
        "--golden",
        str(fixtures_dir / "golden_synthetic.jsonl"),
        "--out",
        str(tmp_path / "reports"),
    ]

    code = main(argv)

    assert code == EXIT_BAD_INPUT
    assert "model.base.path is not set" in capsys.readouterr().err


# --- Hand-worked values (T012) ---


def test_overall_measures_equal_the_hand_worked_values(tmp_path, fixtures_dir):
    run(tmp_path, fixtures_dir)

    report = load_report(tmp_path)
    config = report["configs"][0]
    overall = config["overall"]
    assert (overall["tp"], overall["fp"], overall["tn"], overall["fn"]) == (4, 1, 4, 1)
    assert overall["recall"] == pytest.approx(0.8)
    assert overall["precision"] == pytest.approx(0.8)
    assert overall["false_alarm_rate"] == pytest.approx(0.2)
    assert overall["pr_auc"] == pytest.approx(0.74)
    assert overall["reliable"] is True
    assert config["counts"] == {
        "in_file": 10,
        "malformed": 0,
        "unlabelled": 0,
        "not_evaluable": 0,
        "evaluated": 10,
        "labelled_failures": 5,
    }
    assert config["threshold"] == 0.5
    assert report["golden_file"] == "golden_synthetic.jsonl"
    assert len(report["golden_sha256"]) == 64


def test_category_measures_equal_the_hand_worked_values(tmp_path, fixtures_dir):
    run(tmp_path, fixtures_dir)

    categories = load_report(tmp_path)["configs"][0]["by_category"]
    cards, loans = categories["cards"], categories["loans"]
    assert (cards["tp"], cards["fp"], cards["tn"], cards["fn"]) == (2, 1, 2, 0)
    assert cards["recall"] == pytest.approx(1.0)
    assert cards["precision"] == pytest.approx(2 / 3)
    assert cards["false_alarm_rate"] == pytest.approx(1 / 3)
    assert (loans["tp"], loans["fp"], loans["tn"], loans["fn"]) == (2, 0, 2, 1)
    assert loans["recall"] == pytest.approx(2 / 3)
    assert loans["precision"] == pytest.approx(1.0)
    assert loans["false_alarm_rate"] == pytest.approx(0.0)


def test_predictions_per_item_equal_the_hand_worked_values(tmp_path, fixtures_dir):
    run(tmp_path, fixtures_dir)

    items = load_report(tmp_path)["configs"][0]["items"]
    flagged = [item["item_id"] for item in items if item["predicted_failure"]]
    assert flagged == ["g-05", "g-06", "g-07", "g-08", "g-10"]


def strip_run_details(value):
    """Remove what legitimately differs between two runs: the run ID, the date, and timings."""
    varying = {"run_id", "date", "seconds", "mean_seconds", "p95_seconds"}
    if isinstance(value, dict):
        return {k: strip_run_details(v) for k, v in value.items() if k not in varying}
    if isinstance(value, list):
        return [strip_run_details(v) for v in value]
    return value


def test_two_runs_give_the_same_report(tmp_path, fixtures_dir):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()

    run(first_dir, fixtures_dir, "--sweep")
    run(second_dir, fixtures_dir, "--sweep")

    assert strip_run_details(load_report(first_dir)) == strip_run_details(load_report(second_dir))


def test_no_text_from_the_items_leaves_the_harness(tmp_path, fixtures_dir, capsys, caplog, sentinel):
    caplog.set_level(logging.DEBUG)

    run(tmp_path, fixtures_dir, "--sweep", "--compare-models")

    folder = report_folder(tmp_path)
    captured = capsys.readouterr()
    assert sentinel not in (folder / "report.md").read_text(encoding="utf-8")
    assert sentinel not in (folder / "report.json").read_text(encoding="utf-8")
    assert sentinel not in captured.out + captured.err
    assert sentinel not in caplog.text
