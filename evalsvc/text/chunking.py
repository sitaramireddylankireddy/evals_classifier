"""Cut evidence into chunks of a bounded size with stable IDs."""

import re
from dataclasses import dataclass

from spacy.language import Language

from evalsvc.config import ChunkingSettings
from evalsvc.interfaces import TokenCounter
from evalsvc.text.nlp import sentence_ranges
from evalsvc.types import Chunk, EvidenceItem

_SENTENCE_ENDINGS = ".!?;,"
_WORD = re.compile(r"\S+\s*")


@dataclass(frozen=True)
class _Unit:
    """A piece of evidence that is kept whole when packing: a sentence or a heading line."""

    start: int
    end: int
    heading: str | None  # the heading text, when the unit is a heading line


def chunk_evidence(
    evidence: list[EvidenceItem],
    counter: TokenCounter,
    nlp: Language,
    settings: ChunkingSettings,
) -> list[Chunk]:
    heading_patterns = [re.compile(pattern) for pattern in settings.heading_patterns]
    chunks: list[Chunk] = []
    for item in evidence:
        if not item.text.strip():
            continue
        for start, end, heading in _chunk_ranges(item.text, counter, nlp, settings, heading_patterns):
            text = item.text[start:end]
            chunks.append(
                Chunk(
                    chunk_id=f"c{len(chunks) + 1}",
                    evidence_index=item.index,
                    start=start,
                    end=end,
                    text=text,
                    heading=heading,
                    token_count=counter.count(text),
                )
            )
    return chunks


def _chunk_ranges(
    text: str,
    counter: TokenCounter,
    nlp: Language,
    settings: ChunkingSettings,
    heading_patterns: list[re.Pattern[str]],
) -> list[tuple[int, int, str | None]]:
    def tokens(start: int, end: int) -> int:
        return counter.count(text[start:end])

    units = _units(text, nlp, heading_patterns, settings.max_heading_chars)
    units = _split_oversize(text, units, counter, settings.max_tokens)

    ranges: list[tuple[int, int, str | None]] = []
    section_heading: str | None = None
    chunk_start: int | None = None
    chunk_end = 0
    chunk_heading: str | None = None

    for unit in units:
        if chunk_start is not None:
            too_big = tokens(chunk_start, unit.end) > settings.max_tokens
            # A heading starts a new chunk once the current one is big enough to stand alone.
            new_section = (
                unit.heading is not None and tokens(chunk_start, chunk_end) >= settings.min_tokens
            )
            if too_big or new_section:
                ranges.append((chunk_start, chunk_end, chunk_heading))
                chunk_start = None
        if unit.heading is not None:
            section_heading = unit.heading
        if chunk_start is None:
            chunk_start = unit.start
            chunk_heading = section_heading
        chunk_end = unit.end

    if chunk_start is not None:
        ranges.append((chunk_start, chunk_end, chunk_heading))

    # Fold a short final chunk into the one before it when the result still fits.
    if len(ranges) >= 2:
        (prev_start, _, prev_heading), (last_start, last_end, _) = ranges[-2], ranges[-1]
        if (
            tokens(last_start, last_end) < settings.min_tokens
            and tokens(prev_start, last_end) <= settings.max_tokens
        ):
            ranges[-2:] = [(prev_start, last_end, prev_heading)]

    return ranges


def _units(
    text: str,
    nlp: Language,
    heading_patterns: list[re.Pattern[str]],
    max_heading_chars: int,
) -> list[_Unit]:
    """Split text into units that touch end to start, so no character is lost."""
    starts: list[tuple[int, str | None]] = []
    position = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            if _is_heading(stripped, heading_patterns, max_heading_chars):
                indent = len(line) - len(line.lstrip())
                starts.append((position + indent, stripped))
            else:
                starts.extend((position + start, None) for start, _ in sentence_ranges(line, nlp))
        position += len(line) + 1

    if not starts:
        return [_Unit(0, len(text), None)]

    units = []
    for i, (start, heading) in enumerate(starts):
        unit_start = 0 if i == 0 else start
        unit_end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        units.append(_Unit(unit_start, unit_end, heading))
    return units


def _is_heading(line: str, heading_patterns: list[re.Pattern[str]], max_heading_chars: int) -> bool:
    if len(line) > max_heading_chars or line[-1] in _SENTENCE_ENDINGS:
        return False
    return any(pattern.search(line) for pattern in heading_patterns)


def _split_oversize(
    text: str, units: list[_Unit], counter: TokenCounter, max_tokens: int
) -> list[_Unit]:
    """Split any unit longer than max_tokens at whitespace. A single word is never split."""
    result: list[_Unit] = []
    for unit in units:
        if counter.count(text[unit.start : unit.end]) <= max_tokens:
            result.append(unit)
            continue
        piece_start = unit.start
        previous_boundary = unit.start
        heading = unit.heading
        for word in _WORD.finditer(text, unit.start, unit.end):
            boundary = word.end()
            if (
                previous_boundary > piece_start
                and counter.count(text[piece_start:boundary]) > max_tokens
            ):
                result.append(_Unit(piece_start, previous_boundary, heading))
                heading = None
                piece_start = previous_boundary
            previous_boundary = boundary
        result.append(_Unit(piece_start, unit.end, heading))
    return result
