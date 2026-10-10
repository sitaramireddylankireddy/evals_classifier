"""Token counters. The detector's own counter is added with the model wrapper."""


class WhitespaceTokenCounter:
    """Counts whitespace-separated words. For tests and for runs without the model."""

    def count(self, text: str) -> int:
        return len(text.split())
