"""Cabinet auth schemas.

Request/response models for the login+password portal surface. Identity is derived
only from the verified password check or the verified JWT, never from these bodies —
which is why nothing here carries an account id.

`password_hash` appears in no schema in either direction, deliberately, exactly as it
does not on the staff side (`app/schemas/staff_admin.py`).
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Shared with the staff side (`app/schemas/staff_admin.py::_MIN_PASSWORD_LENGTH`).
#: A password issued here is typed by hand off a printed contract, so the floor is
#: about guessability, not about how long it is comfortable to type.
MIN_PASSWORD_LENGTH = 12


class LoginIn(BaseModel):
    """Body for POST /portal/auth/login."""

    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("login")
    @classmethod
    def _normalize_login(cls, value: str) -> str:
        """Fold to the stored shape so `Ivan` signs in as the account `ivan`."""
        return value.strip().lower()


class RegisterIn(BaseModel):
    """Body for POST /portal/auth/register — an access request, not a sign-up.

    No password field: the applicant does not choose their credentials, staff issue
    them. `note` is free text staff read while deciding.
    """

    contact_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=1, max_length=32)
    company_name: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class RegisterAccepted(BaseModel):
    """The ONLY answer POST /portal/auth/register ever gives on acceptance.

    A fixed body with no id and no account: a response that varied by whether the
    phone had applied before would be the enumeration oracle the schema and the
    dropped unique constraint exist to prevent.
    """

    status: str = "received"


class PasswordChangeIn(BaseModel):
    """Body for POST /portal/auth/password."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)


class StepUpIn(BaseModel):
    """Body for POST /portal/auth/step-up — a password re-entry, not a sign-in."""

    password: str


class StepUpOut(BaseModel):
    """How long the unlocked window lasts, so the client can hide the prompt until
    it is actually needed again rather than guessing at the server's policy."""

    expires_in: int


class MeUpdateIn(BaseModel):
    """Body for PATCH /portal/me — profile self-edit."""

    name: str | None = None
    language: str | None = None


class AccountOut(BaseModel):
    """Public view of a UserAccount (never exposes the telegram_user_id bridge).

    `must_change_password` is part of the contract rather than an internal detail:
    the cabinet routes on it, and after a hard reload `GET /portal/me` is the only
    place the client can learn it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    login: str | None = None
    name: str | None = None
    language: str
    status: str
    must_change_password: bool = False


class PortalTokenResponse(BaseModel):
    """Response for a successful sign-in / refresh / password change.

    The short-lived portal_access token is in the body; the long-lived
    portal_refresh token is delivered only via the httpOnly portal_session cookie.
    """

    access_token: str
    # noqa S105: "bearer" is the RFC 6750 scheme name, not a credential.
    token_type: str = "bearer"  # noqa: S105
    account: AccountOut


# ── Staff surface (api_admin.py) ──────────────────────────────────────────────


class PortalAccountOut(BaseModel):
    """A cabinet account as STAFF see it. Carries no password field of any kind."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    login: str | None = None
    name: str | None = None
    phone: str
    language: str
    applied_company_name: str | None = None
    application_note: str | None = None
    must_change_password: bool
    credentials_issued_at: datetime.datetime | None = None
    credentials_issued_by: int | None = None
    last_login_at: datetime.datetime | None = None
    created_at: datetime.datetime


class IssueCredentialsIn(BaseModel):
    """Body for issuing credentials.

    `password` is optional, and omitting it is the expected path: a generated
    password is stronger than one a person invents under time pressure, and it is
    going to be copied rather than remembered anyway.
    """

    login: str = Field(min_length=1, max_length=64)
    password: str | None = Field(
        default=None, min_length=MIN_PASSWORD_LENGTH, max_length=256
    )


class RegeneratePasswordIn(BaseModel):
    password: str | None = Field(
        default=None, min_length=MIN_PASSWORD_LENGTH, max_length=256
    )


class IssuedCredentialsOut(BaseModel):
    """The one and only time a plaintext password crosses a wire.

    No route can return it again — the account holds an argon2 hash and nothing
    else — so the screen that renders this must say so, and the only recovery is to
    regenerate.
    """

    account: PortalAccountOut
    login: str
    password: str
