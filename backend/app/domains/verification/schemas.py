"""Client-facing verification views. Extracted from `app/schemas/portal_company.py`.

These are the applicant's side of a verification case, and they are deliberately
narrower than the staff views in `api_admin.py`: a check reports its type, status and
a user-safe `detail` (missing document kinds, human-readable reasons, masked last4)
and nothing about who reviewed it or how the decision was reached. `DocumentOut`
carries no `storage_path` for the same reason — `tests/test_security_pass.py` asserts
that field's absence, so treat it as a contract rather than an omission.
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class CheckOut(BaseModel):
    check_type: str
    status: str
    detail: dict[str, object] | None = None  # user-safe subset (e.g. missing docs)


class CaseOut(BaseModel):
    id: int
    case_type: str
    status: str
    submitted_at: datetime.datetime | None = None
    checks: list[CheckOut] = Field(default_factory=list)


class DocumentOut(BaseModel):
    id: int
    kind: str
    mime_type: str | None = None
    size_bytes: int | None = None
    status: str
    created_at: datetime.datetime
