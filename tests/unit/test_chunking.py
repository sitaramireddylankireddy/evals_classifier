import pytest

from evalsvc.config import ChunkingSettings, SentenceSettings
from evalsvc.text.chunking import chunk_evidence
from evalsvc.text.nlp import build_nlp
from evalsvc.text.tokens import WhitespaceTokenCounter
from evalsvc.types import EvidenceItem

COUNTER = WhitespaceTokenCounter()


@pytest.fixture(scope="module")
def nlp():
    return build_nlp(SentenceSettings())


def sentences(count, first=1):
    """Sentences of exactly eight words each, separated by one space."""
    return " ".join(f"Rule {n} says the fee is waived today." for n in range(first, first + count))


def settings(min_tokens, max_tokens):
    return ChunkingSettings(min_tokens=min_tokens, max_tokens=max_tokens)


def chunk(text, nlp, min_tokens, max_tokens):
    return chunk_evidence([EvidenceItem(index=0, text=text)], COUNTER, nlp, settings(min_tokens, max_tokens))


# --- Packing (T007) ---


def test_chunks_stay_within_the_size_range(nlp):
    text = sentences(40)

    chunks = chunk(text, nlp, 30, 50)

    assert len(chunks) == 7
    assert all(30 <= c.token_count <= 50 for c in chunks[:-1])
    assert chunks[-1].token_count <= 50
    assert all(c.token_count == COUNTER.count(c.text) for c in chunks)


def test_chunk_texts_join_back_to_the_source(nlp):
    text = "  " + sentences(40) + "\n\n" + sentences(15, first=41) + "  \n"

    chunks = chunk(text, nlp, 30, 50)

    assert "".join(c.text for c in chunks) == text


def test_chunk_range_reproduces_its_text(nlp):
    text = sentences(40)

    chunks = chunk(text, nlp, 30, 50)

    assert all(text[c.start : c.end] == c.text for c in chunks)
    assert chunks[0].start == 0
    assert chunks[-1].end == len(text)
    assert all(a.end == b.start for a, b in zip(chunks, chunks[1:]))


def test_short_item_becomes_one_chunk(nlp):
    text = sentences(2)

    chunks = chunk(text, nlp, 30, 50)

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].chunk_id == "c1"
    assert chunks[0].evidence_index == 0


def test_blank_evidence_item_gives_no_chunk(nlp):
    evidence = [EvidenceItem(index=0, text="  \n"), EvidenceItem(index=1, text=sentences(2))]

    chunks = chunk_evidence(evidence, COUNTER, nlp, settings(30, 50))

    assert [(c.chunk_id, c.evidence_index) for c in chunks] == [("c1", 1)]


# --- Size edge cases (T008) ---


def test_oversize_sentence_is_split_and_nothing_is_lost(nlp):
    text = " ".join(f"word{n}" for n in range(120))

    chunks = chunk(text, nlp, 30, 50)

    assert len(chunks) == 3
    assert all(c.token_count <= 50 for c in chunks)
    assert "".join(c.text for c in chunks) == text


def test_short_remainder_is_kept_when_merging_would_not_fit(nlp):
    chunks = chunk(sentences(7), nlp, 30, 50)

    assert [c.token_count for c in chunks] == [48, 8]


def test_short_remainder_is_merged_when_it_fits(nlp):
    text = sentences(5) + "\nFEES AND CHARGES\n" + sentences(1, first=6)

    chunks = chunk(text, nlp, 30, 100)

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].heading is None


# --- Headings and IDs (T009) ---


def test_chunks_carry_the_heading_of_their_section(nlp):
    text = "FEES AND CHARGES\n" + sentences(2) + "\n4.2 Cash withdrawals\n" + sentences(2, first=3)

    chunks = chunk(text, nlp, 5, 50)

    assert [c.heading for c in chunks] == ["FEES AND CHARGES", "4.2 Cash withdrawals"]
    assert chunks[1].text.startswith("4.2 Cash withdrawals")
    # The heading is already the first line, so it is not repeated.
    assert chunks[0].context_text == chunks[0].text


def test_later_chunk_of_a_section_gets_the_heading_in_its_context(nlp):
    text = "FEES AND CHARGES\n" + sentences(4)

    chunks = chunk(text, nlp, 5, 20)

    assert [c.heading for c in chunks] == ["FEES AND CHARGES", "FEES AND CHARGES"]
    assert chunks[1].context_text == "FEES AND CHARGES\n" + chunks[1].text
    assert "".join(c.text for c in chunks) == text


def test_evidence_without_headings_has_no_heading(nlp):
    chunks = chunk(sentences(40), nlp, 30, 50)

    assert all(c.heading is None for c in chunks)


def test_sentence_that_looks_like_a_heading_is_not_one(nlp):
    text = "5 Working days are needed for delivery.\n" + sentences(2)

    chunks = chunk(text, nlp, 5, 50)

    assert all(c.heading is None for c in chunks)


def test_ids_and_texts_are_identical_across_runs(nlp):
    text = "FEES AND CHARGES\n" + sentences(40)

    first = chunk(text, nlp, 30, 50)

    for _ in range(9):
        assert chunk(text, nlp, 30, 50) == first


def test_ids_are_unique_across_evidence_items(nlp):
    evidence = [
        EvidenceItem(index=0, text=sentences(12)),
        EvidenceItem(index=1, text=sentences(12, first=13)),
    ]

    chunks = chunk_evidence(evidence, COUNTER, nlp, settings(30, 50))

    assert [c.chunk_id for c in chunks] == ["c1", "c2", "c3", "c4"]
    assert [c.evidence_index for c in chunks] == [0, 0, 1, 1]
    assert all(evidence[c.evidence_index].text[c.start : c.end] == c.text for c in chunks)
