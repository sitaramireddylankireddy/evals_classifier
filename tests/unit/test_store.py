import pytest

from evalsvc.config import ConfigError, Settings, StoreSettings
from evalsvc.interfaces import ResultStore
from evalsvc.records import GroundednessRecord, ResultRecord
from evalsvc.store.results import FILE_NAME, JsonlResultStore, StoreError, build_store
from evalsvc.types import ModelInfo


def make_record(item_id="a1", evaluated_at="2026-10-10T12:00:00.000000+00:00", verdict="pass"):
    return ResultRecord(
        id=item_id,
        run_id="run-1",
        evaluated_at=evaluated_at,
        model=ModelInfo(name="m", revision="r"),
        evaluable=True,
        groundedness=GroundednessRecord(
            verdict=verdict,
            score=1.0,
            max_span_confidence=0.0,
            max_token_probability=0.05,
            threshold=0.5,
        ),
        metadata={"note": "café £5"},
    )


@pytest.fixture
def store(tmp_path):
    return JsonlResultStore(tmp_path / "store")


def test_store_satisfies_the_protocol(store):
    assert isinstance(store, ResultStore)


def test_written_record_reads_back_equal(store):
    record = make_record()

    store.write(record)

    assert store.get_current("a1") == record
    assert list(store.iter_current()) == [record]


def test_unknown_id_and_empty_store(store):
    assert store.get_current("absent") is None
    assert list(store.iter_current()) == []


def test_two_records_for_one_id_keep_history_and_the_later_one_is_current(store, tmp_path):
    first = make_record(evaluated_at="2026-10-10T12:00:00.000000+00:00", verdict="pass")
    second = make_record(evaluated_at="2026-10-10T12:05:00.000000+00:00", verdict="fail")

    store.write(first)
    store.write(second)

    lines = (tmp_path / "store" / FILE_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert store.get_current("a1") == second
    assert list(store.iter_current()) == [second]


def test_later_line_wins_when_times_are_equal(store):
    first = make_record(verdict="pass")
    second = make_record(verdict="fail")

    store.write(first)
    store.write(second)

    assert store.get_current("a1") == second


def test_iter_current_yields_one_record_per_id(store):
    store.write(make_record("a1"))
    store.write(make_record("a2"))
    store.write(make_record("a1", evaluated_at="2026-10-10T13:00:00.000000+00:00"))

    assert [record.id for record in store.iter_current()] == ["a1", "a2"]


def test_failed_write_is_retried_then_raises(tmp_path, monkeypatch):
    store = JsonlResultStore(tmp_path / "store", write_retries=3)
    attempts = []

    def always_fail(line):
        attempts.append(line)
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "_append", always_fail)

    with pytest.raises(StoreError, match="Could not write"):
        store.write(make_record())

    assert len(attempts) == 4


def test_write_succeeds_when_a_retry_works(tmp_path, monkeypatch):
    store = JsonlResultStore(tmp_path / "store", write_retries=3)
    real_append = store._append
    attempts = []

    def fail_once(line):
        attempts.append(line)
        if len(attempts) == 1:
            raise OSError("disk busy")
        real_append(line)

    monkeypatch.setattr(store, "_append", fail_once)

    store.write(make_record())

    assert len(attempts) == 2
    assert store.get_current("a1") is not None


def test_build_store_creates_the_folder(tmp_path):
    folder = tmp_path / "nested" / "store"

    store = build_store(Settings(store=StoreSettings(path=str(folder))))

    assert folder.is_dir()
    assert isinstance(store, JsonlResultStore)


def test_unknown_store_kind_gives_a_clear_error(tmp_path):
    settings = Settings(store=StoreSettings(kind="cloud", path=str(tmp_path)))

    with pytest.raises(ConfigError, match="cloud"):
        build_store(settings)
