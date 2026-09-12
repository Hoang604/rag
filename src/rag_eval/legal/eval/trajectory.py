"""Trajectory evaluation: what an agent costs, not what one ranker returns.

Every other harness here measures a single call to `hybrid_search` and scores
the list it returns. That is the right way to compare two rankers, and it is
the wrong way to describe this system, because the system is an agent that
calls several tools, reads what comes back, and decides what to do next.
NDCG over one shot understates it -- an answer found on the second call counts
as a miss -- and says nothing about the two costs a user actually pays: how
many round trips it took and how much text had to be read.

So a trajectory is recorded rather than a ranking: which tools were called, in
what order, how many bytes came back, how long it took, and whether the
citation the agent finally produced is the right one and quotes the statute
exactly.

Policies are pluggable because the honest ones are not reproducible. A real
language model picks different tools on different days (§4.3 of the feasibility
report), so the number it produces cannot be compared across versions of the
retrieval engine. `ScriptedPolicy` exists for that: it is deterministic, it
uses the same tools in a fixed order, and it gives a floor that moves only when
retrieval moves. Run a model-driven policy for the number that describes the
product; run the scripted one for the number that describes the change.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from rag_eval.legal.eval.smoke_runner import GroundTruth, _check_article_match
from rag_eval.legal.ingestion.facets import PENALTY, classify_intent
from rag_eval.legal.ingestion.xref import address_of_path
from rag_eval.legal.mcp.tools import LegalMCPTools, SearchHit

# Rough token count for Vietnamese under a subword tokeniser. Bytes would
_CHARS_PER_TOKEN = 3.5


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result_chars: int
    elapsed_ms: float


@dataclass
class Trajectory:
    """Everything one question cost, and what it produced."""

    question: str
    calls: list[ToolCall] = field(default_factory=list)
    cited_path: str | None = None
    quoted_text: str | None = None
    gave_up: bool = False

    @property
    def tool_calls(self) -> int:
        return len(self.calls)

    @property
    def tokens_read(self) -> int:
        return int(sum(c.result_chars for c in self.calls) / _CHARS_PER_TOKEN)

    @property
    def elapsed_ms(self) -> float:
        return sum(c.elapsed_ms for c in self.calls)


class RecordingTools:
    """Wraps the MCP tools, records every call, and holds the verdict.

    The policy is handed this instead of `LegalMCPTools`, so it cannot make an
    unmetered call: anything not on this surface is not reachable. It also owns
    the trajectory, so a policy reports its answer through `cite`/`abstain`
    rather than assembling a result object of its own.
    """

    def __init__(self, tools: LegalMCPTools, question: str) -> None:
        self._tools = tools
        self.trajectory = Trajectory(question=question)

    def cite(self, path: str, quoted_text: str) -> None:
        self.trajectory.cited_path = path
        self.trajectory.quoted_text = quoted_text

    def abstain(self) -> None:
        self.trajectory.gave_up = True

    async def _record(self, name: str, arguments: dict[str, Any], coro: Any) -> Any:
        started = time.perf_counter()
        result = await coro
        elapsed = (time.perf_counter() - started) * 1000.0
        payload = (
            result.model_dump_json()
            if hasattr(result, "model_dump_json")
            else str(result)
        )
        self.trajectory.calls.append(
            ToolCall(
                name=name,
                arguments=arguments,
                result_chars=len(payload),
                elapsed_ms=elapsed,
            )
        )
        return result

    async def hybrid_search(
        self, query: str, temporal_violation_date: str | None = None, limit: int = 10
    ) -> Any:
        return await self._record(
            "hybrid_search",
            {"query": query, "limit": limit},
            self._tools.hybrid_search(
                query=query,
                temporal_violation_date=temporal_violation_date,
                limit=limit,
            ),
        )

    async def verbatim_grep(self, pattern: str, limit: int = 20) -> Any:
        return await self._record(
            "verbatim_grep",
            {"pattern": pattern, "limit": limit},
            self._tools.verbatim_grep(pattern=pattern, limit=limit),
        )

    async def hierarchical_navigate(
        self, path: str, direction: str = "FULL_ARTICLE"
    ) -> Any:
        return await self._record(
            "hierarchical_navigate",
            {"path": path, "direction": direction},
            self._tools.hierarchical_navigate(path=path, direction=direction),
        )


class Policy(Protocol):
    """Decides which tools to call for a question and what to cite."""

    name: str

    async def run(self, tools: RecordingTools, question: str) -> None: ...


# A penalty clause states its bracket in full dong.
_MONEY = re.compile(r"\b\d{1,3}(?:\.\d{3}){1,3}\b")

# `classify_intent` is built for ranking, where treating a near-penalty
_ASKS_SUM = re.compile(
    r"(phạt\s+(bao nhiêu|tiền|thế nào|ra sao)|mức phạt|bị phạt|xử phạt)",
    re.IGNORECASE,
)
_ASKS_SOMETHING_ELSE = re.compile(
    r"(bao nhiêu\s+(lần|hình thức|ngày|năm|tháng|điểm|người|chỗ)"
    r"|mấy\s+lần|cơ quan nào|ai\s+(có thẩm quyền|cấp)|thẩm quyền)",
    re.IGNORECASE,
)


def _asks_for_a_sum(question: str) -> bool:
    """Whether the answer to this question has to be an amount of money."""
    if _ASKS_SOMETHING_ELSE.search(question):
        return False
    return classify_intent(question) == PENALTY and bool(_ASKS_SUM.search(question))


class ScriptedPolicy:
    """Cites the top hit and stops. The floor every other policy must beat.

    Deliberately unclever: it exists so that a change in the trajectory numbers
    can only have come from a change in retrieval, which is what a model-driven
    policy cannot promise. Its success rate is Hit@1 by construction.
    """

    name = "top-hit"

    def __init__(self, limit: int = 5) -> None:
        self._limit = limit

    async def run(self, tools: RecordingTools, question: str) -> None:
        result = await tools.hybrid_search(query=question, limit=self._limit)
        hits: list[SearchHit] = list(result.hits)
        if not hits or getattr(result, "confidence", "high") == "none":
            tools.abstain()
            return
        tools.cite(hits[0].path, hits[0].contextualized_text)


class VerifyingPolicy:
    """Checks the cited provision actually answers, and looks further if not.

    A question asking "phạt bao nhiêu" is only answered by text that states an
    amount, and the leaf provision usually does not: the offence is written in
    the Điểm while the bracket that prices it sits in the parent Khoản. Only 85
    of 4,338 points carry a figure in their own text.

    The hierarchy prefix normally carries it down, so the first move is to read
    that rather than the bare clause. When even the prefix has no figure the
    policy spends a second call walking up the tree, which is the behaviour a
    single-shot metric cannot see and cannot credit.
    """

    name = "verify-answerable"

    def __init__(self, limit: int = 5) -> None:
        self._limit = limit

    async def run(self, tools: RecordingTools, question: str) -> None:
        result = await tools.hybrid_search(query=question, limit=self._limit)
        hits: list[SearchHit] = list(result.hits)
        if not hits or getattr(result, "confidence", "high") == "none":
            tools.abstain()
            return

        best = hits[0]
        text = best.contextualized_text
        tools.cite(best.path, text)

        if not _asks_for_a_sum(question) or _MONEY.search(text):
            return

        # The prefix did not carry a figure. Walk up before giving an answer
        parent = await tools.hierarchical_navigate(
            path=best.path, direction="PARENT_CHAIN"
        )
        # Nearest ancestor first: the Khoản that prices the offence, not the
        for node in sorted(parent.nodes, key=lambda n: -n.relative_depth):
            if _MONEY.search(node.verbatim_text):
                tools.cite(best.path, node.verbatim_text)
                return


@dataclass
class TrajectoryScore:
    """Aggregate of one policy over one question set."""

    policy: str
    total: int
    solved: int
    abstained: int
    exact_citations: int
    amount_asked: int
    amount_carried: int
    tool_calls: int
    tokens_read: int
    elapsed_ms: float

    @property
    def success_rate(self) -> float:
        return self.solved / self.total if self.total else 0.0

    @property
    def citation_exactness(self) -> float:
        return self.exact_citations / self.solved if self.solved else 0.0

    @property
    def answer_carried(self) -> float:
        """Of questions asking a penalty, how many citations state one.

        Hit@k cannot express this. A retrieval that returns the right Điểm
        scores a hit while handing the reader text that never says how much.
        """
        return self.amount_carried / self.amount_asked if self.amount_asked else 0.0

    @property
    def calls_per_question(self) -> float:
        return self.tool_calls / self.total if self.total else 0.0

    @property
    def tokens_per_question(self) -> float:
        return self.tokens_read / self.total if self.total else 0.0

    @property
    def ms_per_question(self) -> float:
        return self.elapsed_ms / self.total if self.total else 0.0


def _cited_correctly(trajectory: Trajectory, truth: GroundTruth) -> bool:
    if not trajectory.cited_path:
        return False
    hit = SearchHit(
        chunk_id="",
        doc_code=trajectory.cited_path.split(".", 1)[0],
        doc_title="",
        path=trajectory.cited_path,
        verbatim_text=trajectory.quoted_text or "",
        contextualized_text="",
        metadata={},
        effective_date="",
        expiration_date=None,
        score=0.0,
    )
    return _check_article_match(hit, truth)


def _cited_exactly(trajectory: Trajectory, truth: GroundTruth) -> bool:
    """Whether the citation names the clause, not merely the right article."""
    if not trajectory.cited_path:
        return False
    address = address_of_path(trajectory.cited_path)
    if truth.clause is None:
        return True
    return str(address.khoan or "") == str(truth.clause)


async def score_policy(
    tools: LegalMCPTools,
    policy: Policy,
    items: list[dict[str, Any]],
) -> tuple[TrajectoryScore, list[Trajectory]]:
    """Runs a policy over every question and aggregates what it cost."""
    trajectories: list[Trajectory] = []
    solved = abstained = exact = 0
    amount_asked = amount_carried = 0

    for item in items:
        question = str(item["query"])
        recorder = RecordingTools(tools, question)
        await policy.run(recorder, question)
        trajectory = recorder.trajectory
        trajectories.append(trajectory)

        if _asks_for_a_sum(question):
            amount_asked += 1
            if trajectory.quoted_text and _MONEY.search(trajectory.quoted_text):
                amount_carried += 1

        if trajectory.gave_up:
            abstained += 1
            continue
        truth = GroundTruth.model_validate(item["ground_truth"])
        if _cited_correctly(trajectory, truth):
            solved += 1
            if _cited_exactly(trajectory, truth):
                exact += 1

    return (
        TrajectoryScore(
            policy=policy.name,
            total=len(items),
            solved=solved,
            abstained=abstained,
            exact_citations=exact,
            amount_asked=amount_asked,
            amount_carried=amount_carried,
            tool_calls=sum(t.tool_calls for t in trajectories),
            tokens_read=sum(t.tokens_read for t in trajectories),
            elapsed_ms=sum(t.elapsed_ms for t in trajectories),
        ),
        trajectories,
    )
