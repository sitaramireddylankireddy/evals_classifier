from evalsvc.interfaces import TokenCounter
from evalsvc.text.tokens import WhitespaceTokenCounter


def test_whitespace_counter_satisfies_the_protocol():
    assert isinstance(WhitespaceTokenCounter(), TokenCounter)


def test_whitespace_counter_counts_words():
    counter = WhitespaceTokenCounter()

    assert counter.count("The limit is £500.") == 4
    assert counter.count("  spaced \t out\n\nwords  ") == 3
    assert counter.count("") == 0
    assert counter.count("   ") == 0
