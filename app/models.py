from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RULES = {
    "NAME_MISMATCH", "ADDRESS_MISMATCH", "PERMIT_EXPIRED",
    "PERMIT_EXPIRES_DURING_LEASE", "LEASE_PERIOD_INVALID",
    "ENROLLMENT_YEAR_MISMATCH", "MISSING_DOCUMENT", "MISSING_FIELD",
    "LOW_CONFIDENCE",
}
DOC_IDS = {"lease", "rib", "enrollment", "permit"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(StrictModel):
    page: int = Field(ge=1)
    quote: str


class FieldValue(StrictModel):
    value: str | None
    confidence: float = Field(ge=0, le=1)
    source: Source


class DocumentFacts(StrictModel):
    doc_id: str
    fields: dict[str, FieldValue]

    @field_validator("doc_id")
    @classmethod
    def valid_doc(cls, value: str) -> str:
        if value not in DOC_IDS:
            raise ValueError(f"Unknown document id: {value}")
        return value


class Facts(StrictModel):
    case_id: str
    documents: list[DocumentFacts]

    @field_validator("documents")
    @classmethod
    def unique_docs(cls, value: list[DocumentFacts]) -> list[DocumentFacts]:
        ids = [doc.doc_id for doc in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate document ids")
        return value


class Evidence(StrictModel):
    doc_id: str
    field: str
    value: str | None
    quote: str


class Finding(StrictModel):
    id: str
    severity: Literal["error", "warning", "info"]
    rule: str
    message: str
    evidence: list[Evidence]
    suggested_action: str

    @field_validator("rule")
    @classmethod
    def allowed_rule(cls, value: str) -> str:
        if value not in RULES:
            raise ValueError(f"Unsupported finding rule: {value}")
        return value


class Findings(StrictModel):
    findings: list[Finding]
    missing_documents: list[str]
    ready_to_submit: bool

    @field_validator("missing_documents")
    @classmethod
    def valid_missing_docs(cls, value: list[str]) -> list[str]:
        if any(doc not in DOC_IDS for doc in value):
            raise ValueError("Unknown missing document id")
        return value


class EmailDraft(StrictModel):
    to_role: Literal["student"]
    subject: str
    body_fr: str


class ActionDraft(StrictModel):
    form: dict[str, object]
    email: EmailDraft
    notes_for_staff: list[str]


class ApprovalRequest(StrictModel):
    reviewed: bool


class CreateCaseRequest(StrictModel):
    demo_case_id: str


class AgentReplyError(ValueError):
    pass


def parse_reply(text: str, model: type[BaseModel]) -> BaseModel:
    import json
    import re

    blocks = re.findall(r"```(.*?)```", text, flags=re.DOTALL)
    candidate = None
    for block in blocks:
        content = block.strip()
        if content.startswith("{"):
            candidate = content
            break
        if content.lower().startswith("json"):
            content = content[4:].lstrip()
            if content.startswith("{"):
                candidate = content
                break
    if candidate is None and not blocks:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end >= start:
            candidate = text[start:end + 1]
    if candidate is None:
        raise AgentReplyError("Agent reply contains no JSON object")
    try:
        return model.model_validate(json.loads(candidate))
    except Exception as exc:
        raise AgentReplyError(f"Agent reply JSON did not validate: {exc}") from exc
