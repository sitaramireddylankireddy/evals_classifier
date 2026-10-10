"""Finders for amounts, dates, percentages, and references, with character offsets."""

import re
from functools import lru_cache

from evalsvc.config import ChecksSettings
from evalsvc.types import Match

# Symbols written before a number, and words written after it, per currency code.
_CURRENCY_FORMS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "GBP": (("£",), ("pounds", "pound", "pence", "p")),
    "USD": (("$",), ("dollars", "dollar", "cents", "cent")),
    "EUR": (("€",), ("euros", "euro", "cents", "cent")),
}

_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


@lru_cache
def _amount_regex(currencies: tuple[str, ...]) -> re.Pattern[str]:
    before: list[str] = []
    after: list[str] = []
    for code in currencies:
        symbols, words = _CURRENCY_FORMS.get(code, ((), ()))
        before.extend(re.escape(symbol) for symbol in symbols)
        before.append(re.escape(code) + r"\s?")
        after.append(re.escape(code))
        after.extend(words)
    after.sort(key=len, reverse=True)
    prefixed = rf"(?<!\w)(?:{'|'.join(before)}){_NUMBER}"
    suffixed = rf"(?<![\w.,]){_NUMBER}\s?(?:{'|'.join(after)})\b"
    return re.compile(f"{prefixed}|{suffixed}")


def find_amounts(text: str, currencies: list[str]) -> list[Match]:
    if not currencies:
        return []
    return [
        Match(start=m.start(), end=m.end(), text=m.group(), kind="amount")
        for m in _amount_regex(tuple(currencies)).finditer(text)
    ]


_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"
)
_ORDINAL = r"(?:st|nd|rd|th)?"

# Two-digit years are accepted only with slashes. With hyphens they look like
# sort codes, and with dots like section numbers.
_DATE = re.compile(
    r"\b(?P<iso>\d{4}-\d{2}-\d{2})\b"
    r"|\b(?P<numeric>\d{1,2}/\d{1,2}/\d{2}(?:\d{2})?|\d{1,2}[.-]\d{1,2}[.-]\d{4})\b"
    rf"|\b(?P<day_first>\d{{1,2}}){_ORDINAL}\s+(?:of\s+)?{_MONTH}(?:,?\s+\d{{4}})?\b"
    rf"|\b{_MONTH}\s+(?P<month_first>\d{{1,2}}){_ORDINAL}(?:,?\s+\d{{4}})?\b"
)


def _plausible_date(match: re.Match[str]) -> bool:
    if match.group("iso"):
        _, month, day = (int(part) for part in match.group("iso").split("-"))
        return 1 <= month <= 12 and 1 <= day <= 31
    if match.group("numeric"):
        first, second = (int(part) for part in re.split(r"[/.-]", match.group("numeric"))[:2])
        day_first = 1 <= first <= 31 and 1 <= second <= 12
        month_first = 1 <= first <= 12 and 1 <= second <= 31
        return day_first or month_first
    day = int(match.group("day_first") or match.group("month_first"))
    return 1 <= day <= 31


def find_dates(text: str) -> list[Match]:
    return [
        Match(start=m.start(), end=m.end(), text=m.group(), kind="date")
        for m in _DATE.finditer(text)
        if _plausible_date(m)
    ]


_PERCENTAGE = re.compile(r"(?<![\w.,])\d+(?:\.\d+)?\s?(?:%|per\s?cent\b)")


def find_percentages(text: str) -> list[Match]:
    return [
        Match(start=m.start(), end=m.end(), text=m.group(), kind="percentage")
        for m in _PERCENTAGE.finditer(text)
    ]


def find_references(text: str, patterns: list[str]) -> list[Match]:
    found = [
        Match(start=m.start(), end=m.end(), text=m.group(), kind="reference")
        for pattern in patterns
        for m in re.finditer(pattern, text)
        if m.end() > m.start()
    ]
    # Longest match first at each position, then drop anything overlapping an earlier match.
    found.sort(key=lambda match: (match.start, -match.end))
    result: list[Match] = []
    for match in found:
        if not result or match.start >= result[-1].end:
            result.append(match)
    return result


def has_checkable_value(text: str, checks: ChecksSettings) -> bool:
    """True when the text holds an amount, a date, a percentage, or a reference."""
    return bool(
        find_amounts(text, checks.currencies)
        or find_dates(text)
        or find_percentages(text)
        or find_references(text, checks.reference_patterns)
    )
