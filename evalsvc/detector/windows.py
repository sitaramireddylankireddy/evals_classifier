"""Window planning for large evidence, and combining the detector's per-window output."""

from evalsvc.types import Sentence, Span, TokenScore


def plan_windows(costs: list[int], capacity: int, overlap_tokens: int) -> list[tuple[int, int]]:
    """Group consecutive chunks into overlapping windows.

    `costs` holds the token cost of each chunk. Returns index ranges
    (start, end), end not included. A window holds whole chunks, stays within
    `capacity`, and repeats at least `overlap_tokens` from the end of the
    window before it when that still leaves room for a new chunk. A chunk that
    is larger than `capacity` gets a window to itself.
    """
    count = len(costs)
    if count == 0:
        return []

    windows: list[tuple[int, int]] = []
    start = 0
    while True:
        end = start + 1
        total = costs[start]
        while end < count and total + costs[end] <= capacity:
            total += costs[end]
            end += 1
        windows.append((start, end))
        if end == count:
            return windows

        next_start = end
        repeated = 0
        while next_start - 1 > start and repeated < overlap_tokens:
            next_start -= 1
            repeated += costs[next_start]
        # Give up overlap until the next new chunk fits, so every window moves forward.
        while next_start < end and sum(costs[next_start:end]) + costs[end] > capacity:
            next_start += 1
        start = next_start


def aggregate_min(per_window: list[list[TokenScore]]) -> list[TokenScore]:
    """Combine windows by keeping each token's lowest probability.

    A token counts as supported if any window supports it.
    """
    if not per_window:
        return []
    first = per_window[0]
    for scores in per_window[1:]:
        if len(scores) != len(first) or any(
            (a.start, a.end) != (b.start, b.end) for a, b in zip(first, scores)
        ):
            raise ValueError("Windows returned different answer tokens")
    return [
        TokenScore(
            start=token.start,
            end=token.end,
            prob=min(scores[i].prob for scores in per_window),
        )
        for i, token in enumerate(first)
    ]


def merge_spans(
    tokens: list[TokenScore], answer: str, threshold: float, sentences: list[Sentence]
) -> list[Span]:
    """Merge neighbouring tokens above the threshold into spans."""
    factual = [(sentence.start, sentence.end) for sentence in sentences if sentence.factual]
    spans: list[Span] = []
    run: list[TokenScore] = []
    for token in tokens:
        if token.prob > threshold:
            run.append(token)
        elif run:
            spans.append(_span(run, answer, factual))
            run = []
    if run:
        spans.append(_span(run, answer, factual))
    return spans


def _span(run: list[TokenScore], answer: str, factual: list[tuple[int, int]]) -> Span:
    start, end = run[0].start, run[-1].end
    return Span(
        start=start,
        end=end,
        text=answer[start:end],
        confidence=max(token.prob for token in run),
        excluded=not any(s < end and start < e for s, e in factual),
    )
