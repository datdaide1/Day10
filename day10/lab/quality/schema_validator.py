"""
Pydantic schema validator cho cleaned rows — Bonus +2 / Distinction (a).

Validate toàn bộ schema cleaned rows bằng Pydantic v2 trước khi embed,
đảm bảo type safety và format constraints.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Tuple

try:
    from pydantic import BaseModel, Field, field_validator, ValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False

from quality.expectations import ExpectationResult


_ISO_DATE_FORMAT = "%Y-%m-%d"

ALLOWED_DOC_IDS_SET = frozenset({
    "policy_refund_v4",
    "sla_p1_2026",
    "it_helpdesk_faq",
    "hr_leave_policy",
    "access_control_sop",
})


class CleanedRow(BaseModel):
    """Pydantic model cho một cleaned chunk row."""

    chunk_id: str = Field(min_length=8, description="Stable chunk ID (sha256 hash)")
    doc_id: str = Field(description="Document source ID — must be in allowlist")
    chunk_text: str = Field(min_length=8, description="Cleaned chunk text")
    effective_date: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Effective date in ISO YYYY-MM-DD format",
    )
    exported_at: str = Field(description="Export timestamp (may be empty for legacy data)")

    @field_validator("doc_id")
    @classmethod
    def doc_id_in_allowlist(cls, v: str) -> str:
        if v not in ALLOWED_DOC_IDS_SET:
            raise ValueError(f"doc_id '{v}' not in allowed list: {sorted(ALLOWED_DOC_IDS_SET)}")
        return v

    @field_validator("chunk_text")
    @classmethod
    def chunk_text_no_noise(cls, v: str) -> str:
        if v.strip().startswith("!!!"):
            raise ValueError("chunk_text starts with noise prefix '!!!'")
        if v.strip().lower().startswith("nội dung không rõ ràng:"):
            raise ValueError("chunk_text starts with noise prefix 'Nội dung không rõ ràng:'")
        return v

    @field_validator("effective_date")
    @classmethod
    def effective_date_valid(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"effective_date '{v}' is not a valid date")
        return v


def validate_with_pydantic(
    cleaned_rows: List[Dict[str, Any]],
) -> Tuple[List[ExpectationResult], List[Dict[str, Any]]]:
    """
    Validate cleaned_rows với Pydantic model.

    Trả về:
        - results: danh sách ExpectationResult (1 entry tổng + chi tiết lỗi)
        - invalid_rows: các row vi phạm kèm lỗi
    """
    if not PYDANTIC_AVAILABLE:
        return [
            ExpectationResult(
                "pydantic_schema_validate",
                False,
                "warn",
                "pydantic not installed — skip schema validation",
            )
        ], []

    errors: List[Dict[str, Any]] = []
    for i, row in enumerate(cleaned_rows):
        try:
            CleanedRow(**row)
        except ValidationError as e:
            errors.append({
                "row_index": i,
                "chunk_id": row.get("chunk_id", ""),
                "doc_id": row.get("doc_id", ""),
                "pydantic_errors": e.errors(include_url=False),
            })

    ok = len(errors) == 0
    result = ExpectationResult(
        "pydantic_schema_validate",
        ok,
        "halt",
        f"schema_violations={len(errors)} / total={len(cleaned_rows)}",
    )
    return [result], errors
