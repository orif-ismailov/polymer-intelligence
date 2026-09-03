"""The counterparty has to exist AT DIDOX before anyone loads an E-IMZO key.

Learned live on 25.08.2026. Every one of our own gates passed — rail, status,
seller, ИКПУ, signer identity — the document was created, the payload was right,
the seller typed their key password, the signature was made and timestamped, and
only then did Didox answer:

    422  ИНН/ПИНФЛ заказчика некорректный. ИНН/ПИНФЛ: 562353400

The counterparty simply is not in the operator's registry. That is knowable
before any of it: `GET /v1/utils/info/{tin}` answers in one call.

Two rules follow, and both are about not lying to the seller:

  * **Unknown counterparty is a BLOCKER, not a surprise.** `_prefill` exists
    precisely so a seller sees every reason at once instead of discovering them
    one password at a time.
  * **A provider that cannot answer is not a verdict.** If the lookup itself
    fails, we say nothing — refusing to let someone send a document because
    Didox is momentarily down would be our outage worn as their finding, the
    same rule `StubGovRegistryClient` and `CompanyNotFound` already encode.
"""

from __future__ import annotations

from typing import Any

import pytest


class _Registry:
    """Stands in for the Didox gateway's `info_by_tin`."""

    def __init__(self, known: set[str] | None = None, raises: Exception | None = None) -> None:
        self.known = known or set()
        self.raises = raises
        self.asked: list[str] = []

    def info_by_tin(self, tin: str) -> Any:
        self.asked.append(tin)
        if self.raises is not None:
            raise self.raises
        return object() if tin in self.known else None


class TestCounterpartyIsCheckedBeforeSigning:
    def test_an_unknown_counterparty_blocks(self) -> None:
        from app.domains.edi.api_portal import _counterparty_blocker

        registry = _Registry(known={"312616547"})
        assert _counterparty_blocker(registry, "562353400") == "counterparty_unknown"

    def test_a_known_counterparty_does_not(self) -> None:
        from app.domains.edi.api_portal import _counterparty_blocker

        registry = _Registry(known={"312616547", "562353400"})
        assert _counterparty_blocker(registry, "562353400") is None

    def test_the_lookup_is_asked_about_the_BUYER(self) -> None:  # noqa: N802
        """The seller is us; it is the other side Didox refuses."""
        from app.domains.edi.api_portal import _counterparty_blocker

        registry = _Registry(known={"562353400"})
        _counterparty_blocker(registry, "562353400")
        assert registry.asked == ["562353400"]

    def test_a_provider_outage_is_not_a_verdict(self) -> None:
        """Our integration being down must not read as "this company is fake"."""
        from app.domains.edi.api_portal import _counterparty_blocker
        from app.integrations.didox import ProviderUnavailable

        registry = _Registry(raises=ProviderUnavailable("gateway down"))
        assert _counterparty_blocker(registry, "562353400") is None

    def test_no_tax_id_is_not_a_lookup(self) -> None:
        from app.domains.edi.api_portal import _counterparty_blocker

        registry = _Registry()
        assert _counterparty_blocker(registry, None) is None
        assert registry.asked == []


class _Baskets:
    """Stands in for `class_packages(tin, code)` — the per-company ИКПУ basket."""

    def __init__(self, has: bool = True, raises: Exception | None = None) -> None:
        self.has = has
        self.raises = raises
        self.asked: list[tuple[str, str]] = []

    def class_packages(
        self,
        tax_id: str,
        class_code: str,
        *,
        locale: str = "ru",
        user_key: str | None = None,
    ) -> list[tuple[str, str]]:
        self.asked.append((tax_id, class_code))
        if self.raises is not None:
            raise self.raises
        if not self.has:
            from app.integrations.didox import DidoxError

            raise DidoxError(422, f"[{class_code}] танланган МХИКлар рўйхатида мавжуд эмас")
        return [("1644530", "тонна")]


class TestTheCounterpartyMustHaveDeclaredTheCode:
    """The gate BEHIND the tax id, found on 25.08.2026 by getting past the first.

    With Didox's own `310529901` as the buyer the ИНН check passed and `/sign`
    answered `[03902001002000002] не включены в список избранных ИКПУ!`. The code
    is in OUR basket (`class_packages` confirms it) and not in theirs — so a
    Didox document can only go to a counterparty who has already declared that
    ИКПУ in their own account, and we cannot fill someone else's basket.
    """

    def test_a_counterparty_without_the_code_blocks(self) -> None:
        from app.domains.edi.api_portal import _counterparty_ikpu_blocker

        baskets = _Baskets(has=False)
        assert (
            _counterparty_ikpu_blocker(baskets, "310529901", "03902001002000002")
            == "counterparty_ikpu_missing"
        )

    def test_a_counterparty_who_has_it_does_not(self) -> None:
        from app.domains.edi.api_portal import _counterparty_ikpu_blocker

        assert _counterparty_ikpu_blocker(_Baskets(has=True), "310529901", "0390") is None

    def test_it_asks_about_the_BUYER_not_us(self) -> None:  # noqa: N802
        from app.domains.edi.api_portal import _counterparty_ikpu_blocker

        baskets = _Baskets()
        _counterparty_ikpu_blocker(baskets, "310529901", "03902001002000002")
        assert baskets.asked == [("310529901", "03902001002000002")]

    def test_nothing_to_check_is_not_a_blocker(self) -> None:
        """No ИКПУ yet is already reported as `ikpu_missing`; saying it twice
        would read as two separate problems."""
        from app.domains.edi.api_portal import _counterparty_ikpu_blocker

        baskets = _Baskets()
        assert _counterparty_ikpu_blocker(baskets, "310529901", None) is None
        assert _counterparty_ikpu_blocker(baskets, None, "0390") is None
        assert baskets.asked == []

    def test_a_provider_outage_is_not_a_verdict(self) -> None:
        from app.domains.edi.api_portal import _counterparty_ikpu_blocker
        from app.integrations.didox import ProviderUnavailable

        baskets = _Baskets(raises=ProviderUnavailable("down"))
        assert _counterparty_ikpu_blocker(baskets, "310529901", "0390") is None


class TestTheRefusalReachesThePerson:
    """Didox's 422 carries the only sentence that says what to do about it."""

    def test_the_provider_message_survives_the_translation(self) -> None:
        from app.domains.edi.api_portal import _provider_error
        from app.integrations.didox import DidoxError

        exc = DidoxError(422, "ИНН/ПИНФЛ заказчика некорректный. ИНН/ПИНФЛ: 562353400")
        http = _provider_error(exc)
        assert http.status_code == 422
        assert isinstance(http.detail, dict)
        assert http.detail["error"] == "didox_rejected"
        assert "562353400" in str(http.detail["message"])

    def test_their_own_remedy_text_is_not_dropped(self) -> None:
        """`errorDetails.description` is Didox saying what to DO — the most
        useful sentence they ever send, and we were throwing it away."""
        from app.domains.edi.api_portal import _provider_error
        from app.integrations.didox import DidoxError

        exc = DidoxError(
            422,
            "ИНН/ПИНФЛ заказчика некорректный",
            trace_id="abc-123",
            description="Проверьте ИНН контрагента в справочнике",
        )
        detail = _provider_error(exc).detail
        assert isinstance(detail, dict)
        assert detail["description"] == "Проверьте ИНН контрагента в справочнике"
        assert detail["trace_id"] == "abc-123"

    def test_the_portal_has_wording_for_a_provider_refusal(self) -> None:
        """A code with no string renders as the generic «что-то пошло не так»,
        which is what hid this refusal for an afternoon."""
        import json
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2] / "portal/src/shared/i18n/locales"
        for lang in ("ru", "uz", "en"):
            data = json.loads((root / f"{lang}.json").read_text(encoding="utf-8"))
            assert "rejected" in data["didox"]["signErrors"], lang
            assert "counterparty_unknown" in data["didoxDocument"]["blockers"], lang


@pytest.mark.parametrize("blocker", ["counterparty_unknown"])
def test_the_prefill_documents_its_own_blocker_vocabulary(blocker: str) -> None:
    """The schema's docstring is the contract the UI reads; a blocker missing
    from it is one nobody wrote a string for."""
    from app.domains.edi.schemas import DidoxContractPrefillOut

    assert blocker in (DidoxContractPrefillOut.model_fields["blockers"].description or "")
