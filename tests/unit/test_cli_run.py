import json
import logging

from evalsvc.cli.run import EXIT_BAD_INPUT, EXIT_OK, EXIT_RUN_FAILED, main
from evalsvc.judge import StubLargeJudge
from evalsvc.pipeline import build_components
from evalsvc.store.results import FILE_NAME, JsonlResultStore, StoreError
from tests.fakes import EVIDENCE, SUPPORTED_ANSWER, UNSUPPORTED_ANSWER, FakeDetector


def fake_components(settings):
    return build_components(settings, detector=FakeDetector(), judge=StubLargeJudge())


def write_config(tmp_path):
    path = tmp_path / "config.toml"
    store = (tmp_path / "store").as_posix()
    path.write_text(f'[run]\nsample_rate = 0.0\n[store]\npath = "{store}"\n', encoding="utf-8")
    return path


def write_input(tmp_path, objects):
    path = tmp_path / "items.json"
    path.write_text(json.dumps(objects), encoding="utf-8")
    return path


def obj(item_id, answer=SUPPORTED_ANSWER, evidence=EVIDENCE):
    return {"id": item_id, "question": "alpha question", "evidence": evidence, "answer": answer}


def run(tmp_path, objects, factory=fake_components):
    argv = ["--config", str(write_config(tmp_path)), "--input", str(write_input(tmp_path, objects))]
    return main(argv, components_factory=factory)


def stored(tmp_path):
    return {record.id: record for record in JsonlResultStore(tmp_path / "store").iter_current()}


# --- The command (T013) ---


def test_completed_run_exits_zero_even_with_failed_verdicts(tmp_path, capsys):
    code = run(tmp_path, [obj("a1"), obj("a2", answer=UNSUPPORTED_ANSWER)])

    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "Received: 2 | skipped at input: 0" in out
    assert "Evaluated: 2 | passed: 1 | failed: 1 | not evaluable: 0" in out
    assert "Escalated: 1 | escalation failed: 0" in out
    assert "Model: fake-detector" in out
    records = stored(tmp_path)
    assert records["a1"].groundedness.verdict == "pass"
    assert records["a2"].groundedness.verdict == "fail"
    assert records["a2"].escalated is True


def test_objects_rejected_at_input_are_counted(tmp_path, capsys):
    code = run(tmp_path, [obj("a1"), "not an object", {"id": "a3"}, obj("a4", answer="")])

    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "Received: 4 | skipped at input: 2" in out
    assert "Evaluated: 1 | passed: 1 | failed: 0 | not evaluable: 1" in out
    assert set(stored(tmp_path)) == {"a1", "a4"}


def test_empty_list_exits_zero_and_writes_nothing(tmp_path, capsys):
    code = run(tmp_path, [])

    assert code == EXIT_OK
    assert "Received: 0" in capsys.readouterr().out
    assert not (tmp_path / "store" / FILE_NAME).exists()


def test_jsonl_input_is_accepted(tmp_path):
    path = tmp_path / "items.jsonl"
    path.write_text(json.dumps(obj("a1")) + "\n" + json.dumps(obj("a2")) + "\n", encoding="utf-8")

    code = main(
        ["--config", str(write_config(tmp_path)), "--input", str(path)],
        components_factory=fake_components,
    )

    assert code == EXIT_OK
    assert set(stored(tmp_path)) == {"a1", "a2"}


def test_missing_config_file_exits_with_bad_input(tmp_path, capsys):
    argv = ["--config", str(tmp_path / "absent.toml"), "--input", str(write_input(tmp_path, []))]

    code = main(argv, components_factory=fake_components)

    assert code == EXIT_BAD_INPUT
    assert "Config file not found" in capsys.readouterr().err


def test_invalid_input_file_exits_with_bad_input(tmp_path, capsys, sentinel):
    path = tmp_path / "items.json"
    path.write_text(f'[{{"id": "a1", "answer": "{sentinel}', encoding="utf-8")

    code = main(
        ["--config", str(write_config(tmp_path)), "--input", str(path)],
        components_factory=fake_components,
    )

    captured = capsys.readouterr()
    assert code == EXIT_BAD_INPUT
    assert "not valid JSON" in captured.err
    assert sentinel not in captured.err + captured.out


def test_model_that_is_not_configured_exits_with_bad_input(tmp_path, capsys, monkeypatch):
    from evalsvc import pipeline

    monkeypatch.setattr(pipeline, "gpu_available", lambda: False)
    argv = ["--config", str(write_config(tmp_path)), "--input", str(write_input(tmp_path, []))]

    code = main(argv)

    assert code == EXIT_BAD_INPUT
    assert "model.base.path is not set" in capsys.readouterr().err


def test_store_that_cannot_be_written_stops_the_run(tmp_path, capsys):
    class BrokenStore:
        def write(self, record):
            raise StoreError("Could not write to the result store")

        def get_current(self, item_id):
            return None

        def iter_current(self):
            return iter(())

    def factory(settings):
        return build_components(
            settings, detector=FakeDetector(), judge=StubLargeJudge(), store=BrokenStore()
        )

    code = run(tmp_path, [obj("a1")], factory)

    captured = capsys.readouterr()
    assert code == EXIT_RUN_FAILED
    assert "Run stopped" in captured.err
    assert "Evaluated" not in captured.out


# --- Privacy end to end (T014) ---


def test_customer_text_appears_only_in_the_store(tmp_path, capsys, caplog, sentinel):
    caplog.set_level(logging.DEBUG)
    objects = [
        obj("a1", answer=f"Alpha {sentinel} gamma.", evidence=f"{EVIDENCE} {sentinel}x"),
        obj("a2", answer=f"{sentinel} beta."),
        f"{sentinel} not an object",
    ]

    code = run(tmp_path, objects)

    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert sentinel not in captured.out
    assert sentinel not in captured.err
    assert sentinel not in caplog.text
    store_text = (tmp_path / "store" / FILE_NAME).read_text(encoding="utf-8")
    assert sentinel in store_text


def test_spans_in_stored_records_match_the_original_answer(tmp_path):
    answer = f"Alpha beta. {UNSUPPORTED_ANSWER} Delta zebra epsilon."

    run(tmp_path, [obj("a1", answer=answer)])

    spans = stored(tmp_path)["a1"].groundedness.unsupported_spans
    assert [span.text for span in spans] == ["unicorn", "zebra"]
    assert all(answer[span.start : span.end] == span.text for span in spans)
