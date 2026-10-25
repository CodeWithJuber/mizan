"""Bounded API inputs; authenticated identity is never part of request JSON."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class OwnedRequest(StrictModel):
    system: str = Field(default="", max_length=16000)
    messages: list[Message] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_turns(self):
        if (
            any(
                m.role != ("user" if i % 2 == 0 else "assistant")
                for i, m in enumerate(self.messages)
            )
            or self.messages[-1].role != "user"
        ):
            raise ValueError("Alternating user/assistant turns ending with user are required")
        if len(self.system) + sum(len(m.content) for m in self.messages) > 64000:
            raise ValueError("Request exceeds 64000 characters")
        return self


class ReviewRequest(StrictModel):
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted: bool = Field(strict=True)
    evidence: str = Field(min_length=1, max_length=2000)
    supersedes: str | None = Field(default=None, max_length=64)


class RetractionRequest(StrictModel):
    evidence: str = Field(min_length=1, max_length=2000)


class Observation(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    context: dict[str, str]
    sense: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=1000)


class ContextRequest(StrictModel):
    mode: Literal["finite", "episodic_exists"] = "finite"
    ontology: dict[str, list[str]]
    senses: list[str] = Field(min_length=1, max_length=16)
    language: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=128)
    context: dict[str, str]
    observations: list[Observation] = Field(default_factory=list, max_length=512)
    retract_ids: list[str] = Field(default_factory=list, max_length=512)

    @model_validator(mode="after")
    def bound_payload(self):
        if len(self.model_dump_json()) > 128000:
            raise ValueError("Context request exceeds 128000 characters")
        cells = 1
        for values in self.ontology.values():
            cells *= len(values)
        if cells > 256:
            raise ValueError("API context domain is limited to 256 cells")
        return self


def resolve_context(request: ContextRequest) -> dict:
    from mizan_research.existential_context import ExistentialContextMemory
    from mizan_research.finite_context import FiniteContextMemory

    memory: FiniteContextMemory | ExistentialContextMemory
    if request.mode == "episodic_exists":
        memory = ExistentialContextMemory(request.ontology, request.senses, max_nodes=5000)
    else:
        memory = FiniteContextMemory(request.ontology, request.senses)
    for row in request.observations:
        memory.observe(request.language, request.symbol, row.id, row.context, row.sense, row.source)
    for evidence_id in request.retract_ids:
        if isinstance(memory, ExistentialContextMemory):
            memory.retract(request.language, request.symbol, evidence_id, "explicit API retraction")
        else:
            memory.retract(request.language, request.symbol, evidence_id)
    return dict(memory.resolve(request.language, request.symbol, request.context))
