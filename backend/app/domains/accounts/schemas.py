"""Portal Pydantic schemas (R1 W3 — T3.3).

Request/response models for the passwordless-OTP portal auth surface. Identity is
derived only from the verified OTP / JWT, never from these bodies.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OtpRequestIn(BaseModel):
    """Body for POST /portal/auth/otp/request."""

    phone: str


class OtpVerifyIn(BaseModel):
    """Body for POST /portal/auth/otp/verify."""

    phone: str
    code: str


class MeUpdateIn(BaseModel):
    """Body for PATCH /portal/me — profile self-edit."""

    name: str | None = None
    language: str | None = None


class AccountOut(BaseModel):
    """Public view of a UserAccount (never exposes telegram_user_id bridge)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str | None = None
    language: str
    status: str


class PortalTokenResponse(BaseModel):
    """Response for a successful OTP verify / refresh.

    The short-lived portal_access token is in the body; the long-lived
    portal_refresh token is delivered only via the httpOnly portal_session cookie.
    """

    access_token: str
    # noqa S105: "bearer" is the RFC 6750 scheme name, not a credential.
    token_type: str = "bearer"  # noqa: S105
    account: AccountOut
