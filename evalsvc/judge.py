"""Stand-in for the large judge. The real judge exists outside this service."""

from evalsvc.config import ConfigError, Settings
from evalsvc.interfaces import LargeJudge
from evalsvc.types import JudgeRequest, JudgeResponse

STUB_VERDICT = "not_judged"
STUB_RATIONALE = "Stand-in judge: no judgement was made."


class StubLargeJudge:
    """Returns a fixed response, makes no network call, and remembers what it was asked."""

    def __init__(self, verdict: str = STUB_VERDICT, rationale: str = STUB_RATIONALE) -> None:
        self._response = JudgeResponse(verdict=verdict, rationale=rationale)
        self.requests: list[JudgeRequest] = []

    def judge(self, request: JudgeRequest) -> JudgeResponse:
        self.requests.append(request)
        return self._response


def build_judge(settings: Settings) -> LargeJudge:
    if settings.judge.kind != "stub":
        raise ConfigError(f"Unknown judge kind '{settings.judge.kind}'. Known kinds: stub")
    return StubLargeJudge()
