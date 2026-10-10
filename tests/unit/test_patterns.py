import pytest

from evalsvc.config import ChecksSettings
from evalsvc.text.patterns import (
    find_amounts,
    find_dates,
    find_percentages,
    find_references,
    has_checkable_value,
)

CHECKS = ChecksSettings()


def texts(matches):
    return [match.text for match in matches]


def assert_offsets(text, matches):
    for match in matches:
        assert text[match.start : match.end] == match.text


def test_find_amounts():
    text = "It costs £1,250.00 today, or 150 pounds, or 50p, or GBP 20."

    matches = find_amounts(text, ["GBP"])

    assert texts(matches) == ["£1,250.00", "150 pounds", "50p", "GBP 20"]
    assert {match.kind for match in matches} == {"amount"}
    assert_offsets(text, matches)


def test_amount_at_the_end_of_a_sentence_leaves_out_the_full_stop():
    assert texts(find_amounts("The limit is £500.", ["GBP"])) == ["£500"]


def test_no_currencies_means_no_amounts():
    assert find_amounts("The limit is £500.", []) == []


def test_find_dates():
    text = "Valid from 3 March 2025 until 03/04/2025, then 2025-03-03 and 3rd Mar 2025."

    matches = find_dates(text)

    assert texts(matches) == ["3 March 2025", "03/04/2025", "2025-03-03", "3rd Mar 2025"]
    assert {match.kind for match in matches} == {"date"}
    assert_offsets(text, matches)


def test_date_without_a_year_is_found():
    assert texts(find_dates("Payment is due on 3 March each year.")) == ["3 March"]


@pytest.mark.parametrize("text", ["Paid on 31/13/2025.", "Paid on 45/01/2025.", "Paid on 2025-14-03."])
def test_impossible_numeric_dates_are_not_found(text):
    assert find_dates(text) == []


def test_find_percentages():
    text = "The rate is 19.5% or 5 per cent, not 5 percent."

    matches = find_percentages(text)

    assert texts(matches) == ["19.5%", "5 per cent", "5 percent"]
    assert {match.kind for match in matches} == {"percentage"}
    assert_offsets(text, matches)


def test_find_references():
    text = "See Section 4.2 and clause 7 for details."

    matches = find_references(text, CHECKS.reference_patterns)

    assert texts(matches) == ["Section 4.2", "clause 7"]
    assert {match.kind for match in matches} == {"reference"}
    assert_offsets(text, matches)


def test_overlapping_reference_patterns_give_one_match():
    patterns = [r"Section \d+", r"Section \d+\.\d+"]

    assert texts(find_references("See Section 4.2 now.", patterns)) == ["Section 4.2"]


@pytest.mark.parametrize(
    "text",
    [
        "Thank you for getting in touch with us about your card.",
        "Your account number is 12345678 and your sort code is 20-10-53.",
        "You may call us on any working day and we will help.",
        "The card arrives within 5 working days.",
    ],
)
def test_plain_text_and_account_details_match_nothing(text):
    assert find_amounts(text, ["GBP"]) == []
    assert find_dates(text) == []
    assert find_percentages(text) == []
    assert find_references(text, CHECKS.reference_patterns) == []
    assert has_checkable_value(text, CHECKS) is False


@pytest.mark.parametrize(
    "text",
    ["The fee is £5.", "It starts on 1 March 2025.", "The rate is 5%.", "See section 4.2."],
)
def test_has_checkable_value(text):
    assert has_checkable_value(text, CHECKS) is True
