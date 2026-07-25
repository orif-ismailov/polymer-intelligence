"""
E-IMZO evidence & person KYC data (R3 — ARCHITECTURE §9.6, §6.2).

`SignatureEvidence` is an **immutable, append-only** record of a verified E-IMZO
PKCS#7 signature: the signed challenge, the S3 path of the stored PKCS#7 blob
(+ its sha256 for tamper detection), and the parsed certificate subject. It backs
two purposes — `company_identity` (Stage A wizard confirmation) and `contract`
(Stage B e-contract signing) — so the same signing rails are reused. There is NO
update path: a re-sign writes a new row.

`CompanyPersonData` holds director/signer PII (full name, PINFL) app-layer
encrypted with the same `VERIFICATION_ENC_KEY` scheme as bank accounts (§6.2).
Only `pinfl_last4` is stored in clear (for masked display `****{last4}`); the
full PINFL/name never appear in a response or a log line.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    DateTime,
    ForeignKey,
    LargeBinary,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class SignatureEvidence(Base):
    """Immutable evidence of one verified E-IMZO signature (append-only)."""

    __tablename__ = "signature_evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=False
    )                                                                             # who signed
    purpose: Mapped[str] = mapped_column(Text, nullable=False)                    # 'company_identity' | 'contract'
    challenge: Mapped[str] = mapped_column(Text, nullable=False)                  # the signed nonce
    pkcs7_storage_path: Mapped[str] = mapped_column(Text, nullable=False)         # S3 evidence/eimzo/{company_id}/…
    pkcs7_sha256: Mapped[str] = mapped_column(Text, nullable=False)               # integrity of the stored blob
    cert_subject: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # parsed subject fields
    signed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CompanyPersonData(Base):
    """Encrypted director/signer PII bound to a company (§6.2)."""

    __tablename__ = "company_person_data"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_accounts.id"), nullable=True
    )
    full_name_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)     # Fernet ciphertext
    pinfl_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)         # Fernet ciphertext
    pinfl_last4: Mapped[str | None] = mapped_column(CHAR(4), nullable=True)       # clear, for masking
    position: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="eimzo")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
