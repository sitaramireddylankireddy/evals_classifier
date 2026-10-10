from evalsvc.detector.prompt import format_context, passage_line


def test_question_prompt_for_two_passages():
    prompt = format_context(
        ["The daily limit is £500.", "Limits are reviewed yearly."], "What is the daily limit?"
    )

    assert prompt == (
        "Briefly answer the following question:\n"
        "What is the daily limit?\n"
        "Bear in mind that your response should be strictly based on the following 2 passages:\n"
        "passage 1: The daily limit is £500.\n"
        "passage 2: Limits are reviewed yearly.\n"
        "In case the passages do not contain the necessary information to answer the question,"
        ' please reply with: "Unable to answer based on given passages."\n'
        "output:"
    )


def test_summary_prompt_is_used_when_there_is_no_question():
    expected = "Summarize the following text:\npassage 1: First.\npassage 2: Second.\noutput:"

    assert format_context(["First.", "Second."], None) == expected
    assert format_context(["First.", "Second."], "") == expected
    assert format_context(["First.", "Second."], "   ") == expected


def test_braces_and_dollar_signs_in_the_text_are_kept_as_they_are():
    prompt = format_context(["Fee is ${amount} or {x}."], "Is {this} $ok?")

    assert "passage 1: Fee is ${amount} or {x}." in prompt
    assert "Is {this} $ok?" in prompt


def test_prompt_with_no_passages():
    prompt = format_context([], "What is the daily limit?")

    assert "the following 0 passages:\n\nIn case" in prompt


def test_passage_line():
    assert passage_line(3, "Some text.") == "passage 3: Some text."
