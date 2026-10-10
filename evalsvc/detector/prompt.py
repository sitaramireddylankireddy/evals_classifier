"""The prompt wording the detector was trained with.

Copied from lettucedetect 0.2.3 (prompts/qa_prompt_en.txt, prompts/summary_prompt_en.txt,
and PromptUtils.format_context). It must stay identical to the wording used in training:
a slow test compares it with the installed package.
"""

_QA_TEMPLATE = (
    "Briefly answer the following question:\n"
    "{question}\n"
    "Bear in mind that your response should be strictly based on the following"
    " {num_passages} passages:\n"
    "{context}\n"
    "In case the passages do not contain the necessary information to answer the question,"
    ' please reply with: "Unable to answer based on given passages."\n'
    "output:"
)

_SUMMARY_TEMPLATE = "Summarize the following text:\n{text}\noutput:"


def passage_line(number: int, text: str) -> str:
    return f"passage {number}: {text}"


def format_context(passages: list[str], question: str | None) -> str:
    """Wrap the passages and the question in the training prompt.

    With no question, the summary wording is used, as the package does.
    """
    block = "\n".join(passage_line(i + 1, text) for i, text in enumerate(passages))
    if question is None or not question.strip():
        return _SUMMARY_TEMPLATE.format(text=block)
    return _QA_TEMPLATE.format(question=question, num_passages=len(passages), context=block)
