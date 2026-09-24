"""Every document the rules can REQUIRE must have a slot ON THE FLOW that needs it.

`check_documents_complete` decides what a company must upload; the registration
wizard decides what it can upload. They live in different languages in different
packages and nothing connected them — so a rule could demand a kind the form
never offers, and the applicant would sit at `needs_info` with no control that
could clear it. The wizard is the only upload surface (`CHECK_TO_STEP` sends
`documents_complete` straight back to it), so "no slot" means "no way to comply".

**Per flow, not per product.** The first version of this test unioned all four
kind lists, and that was wrong in a way its own mutation check exposed: removing
`bank_letter` from the default flow did not fail it, because `bank_letter` also
appears in `LOGISTICS_DOC_KINDS`. A buyer cannot upload a document from the
carrier's step. Each flow is therefore checked against the list it actually
renders.

The converse is deliberately NOT asserted: a slot with no rule behind it is
allowed — it lets an applicant volunteer something a reviewer may want — it just
has to be a deliberate choice rather than an accident.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domains.companies.service import (
    ACCOUNT_TYPE_ROLE_SETS,
    InvalidBusinessRoles,
    assert_single_account_type,
)
from app.domains.verification.checks import _ROLE_REQUIRED_DOCS
from app.models.enums import CompanyBusinessRole, VerificationDocumentKind

_CONSTANTS = (
    Path(__file__).resolve().parents[2]
    / "portal"
    / "src"
    / "features"
    / "company-wizard"
    / "model"
    / "constants.ts"
)

_CERT = VerificationDocumentKind.registration_certificate.value

#: role → the constant naming the kinds that role's registration flow renders.
#: The three typed flows prepend `registration_certificate` in their step
#: components (`["registration_certificate", ...KINDS]`) rather than listing it.
_FLOW_FOR_ROLE: dict[CompanyBusinessRole, str] = {
    CompanyBusinessRole.importer: "WIZARD_DOCUMENT_KINDS",
    CompanyBusinessRole.distributor: "WIZARD_DOCUMENT_KINDS",
    CompanyBusinessRole.trader: "WIZARD_DOCUMENT_KINDS",
    CompanyBusinessRole.manufacturer: "MANUFACTURER_CERT_KINDS",
    CompanyBusinessRole.logistics_provider: "LOGISTICS_DOC_KINDS",
    CompanyBusinessRole.laboratory: "LABORATORY_DOC_KINDS",
}


def _kind_list(name: str) -> list[str]:
    """The string members of one exported `DocumentKind[]` array."""
    src = _CONSTANTS.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {re.escape(name)}: readonly DocumentKind\[\] = \[(.*?)\];",
        src,
        re.S,
    )
    assert match, f"{name} not found in {_CONSTANTS}"
    return re.findall(r'"([^"]+)"', match.group(1))


def _offered_on(constant: str) -> set[str]:
    """What one flow can upload — its own list, plus the prepended certificate."""
    return set(_kind_list(constant)) | {_CERT}


class TestEveryFlowCanSupplyWhatItsRulesDemand:
    def test_the_default_flow_offers_both_unconditional_requirements(self) -> None:
        """A buyer or distributor can be required to produce exactly two things:
        the registration certificate (unless E-IMZO locked identity) and, once a
        bank account is added, the bank letter. Both must be on THIS step —
        `bank_letter` existing on the carrier's step is no help to a buyer."""
        offered = _offered_on("WIZARD_DOCUMENT_KINDS")
        for kind in (_CERT, VerificationDocumentKind.bank_letter.value):
            assert kind in offered, (
                f"{kind} can be required of a buyer/distributor but the default "
                f"documents step does not offer it — offered: {sorted(offered)}"
            )

    def test_every_typed_flow_offers_the_registration_certificate(self) -> None:
        for constant in (
            "MANUFACTURER_CERT_KINDS",
            "LOGISTICS_DOC_KINDS",
            "LABORATORY_DOC_KINDS",
        ):
            assert _CERT in _offered_on(constant), constant

    def test_every_reachable_role_required_document_is_on_that_roles_flow(self) -> None:
        """The per-role rules, for roles a company can actually hold, each checked
        against the flow that role registers through.

        Live pairing: laboratory → `certificate`, which sits on the laboratory's
        own step. `_ROLE_REQUIRED_DOCS` also demands `license` of an
        `insurance_provider`, excluded here because that role is unreachable —
        pinned by the test below.
        """
        reachable = {role for allowed in ACCOUNT_TYPE_ROLE_SETS for role in allowed}
        problems: list[str] = []
        for role, kind in _ROLE_REQUIRED_DOCS.items():
            if role not in reachable:
                continue
            constant = _FLOW_FOR_ROLE[role]
            if kind.value not in _offered_on(constant):
                problems.append(f"{role.value}→{kind.value} (not in {constant})")
        assert not problems, (
            f"roles require documents their own flow does not offer: {problems}. "
            "The applicant would be asked for a file with no control to attach it."
        )

    def test_every_reachable_role_has_a_known_flow(self) -> None:
        """Guards the map above: a new account type with no entry here would make
        the role-coverage test silently skip it."""
        reachable = {role for allowed in ACCOUNT_TYPE_ROLE_SETS for role in allowed}
        assert reachable <= set(_FLOW_FOR_ROLE), sorted(reachable - set(_FLOW_FOR_ROLE))


class TestWhyLicenceHasNoSlot:
    def test_insurance_provider_is_unreachable(self) -> None:
        """`license` was dropped from the default wizard because no account type
        maps to `insurance_provider`, so its rule can never fire.

        If that role is ever added to an `ACCOUNT_TYPE_ROLE_SETS` card this fails
        — and the failure is the reminder to put the licence slot back, rather
        than shipping a company asked for a document it cannot attach.
        """
        reachable = {role for allowed in ACCOUNT_TYPE_ROLE_SETS for role in allowed}
        assert CompanyBusinessRole.insurance_provider not in reachable

        with pytest.raises(InvalidBusinessRoles):
            assert_single_account_type([CompanyBusinessRole.insurance_provider])

    def test_director_id_is_required_by_no_rule(self) -> None:
        """The other slot that was removed. It was never in `_ROLE_REQUIRED_DOCS`
        and never in the unconditional set — the director's name comes from the
        state registry and their ПИНФЛ from confirming by key."""
        assert VerificationDocumentKind.director_id not in set(_ROLE_REQUIRED_DOCS.values())
