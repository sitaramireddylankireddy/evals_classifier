import logging

import pytest

from evalsvc.safelog import MAX_STRING_LENGTH, log_event
from evalsvc.types import ReasonCode


def test_allowed_fields_are_logged(caplog):
    caplog.set_level(logging.DEBUG)

    log_event("ingest.skipped", item_id="a1", position=3, reason=ReasonCode.MISSING_FIELD)

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert message.startswith("ingest.skipped ")
    assert '"item_id": "a1"' in message
    assert '"position": 3' in message
    assert '"reason": "missing_field"' in message


def test_fields_with_no_value_are_left_out(caplog):
    caplog.set_level(logging.DEBUG)

    log_event("ingest.skipped", item_id=None, position=0)

    assert "item_id" not in caplog.records[0].getMessage()


def test_level_can_be_set(caplog):
    caplog.set_level(logging.DEBUG)

    log_event("run.failed", level=logging.ERROR, error_code="store_unavailable")

    assert caplog.records[0].levelno == logging.ERROR


def test_field_name_outside_the_allow_list_is_rejected(caplog):
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ValueError, match="answer"):
        log_event("ingest.skipped", answer="The limit is £500.")

    assert caplog.records == []


def test_long_text_is_rejected():
    with pytest.raises(ValueError, match="too long"):
        log_event("ingest.skipped", item_id="x" * (MAX_STRING_LENGTH + 1))


def test_value_that_is_not_text_or_a_number_is_rejected():
    with pytest.raises(TypeError, match="item_id"):
        log_event("ingest.skipped", item_id=["a1"])


def test_event_name_with_free_text_is_rejected():
    with pytest.raises(ValueError, match="Event name"):
        log_event("Skipped the object about a card fee")
