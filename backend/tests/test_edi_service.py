"""The Didox document machine — the parts that need no database (P7.a W6).

Everything asserted here is a rule that fails silently if it is wrong:

  * the bytes handed to the browser must reproduce EXACTLY, or the signature
    covers something Didox will not match;
  * the stash is single-use, so a replayed signature is an expiry rather than a
    second send;
  * status application is FORWARD-ONLY, because the poller's cursor has day
    granularity and is deliberately overlapped — a stale page must not undo an
    activation;
  * `4` (rejected) and `50` (annulled by the tax committee) change no state of
    ours. `active` is terminal and a deal may already be riding on it.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from app.domains.edi import service as edi_service
from app.domains.edi.models import (
    STATUS_ANNULLED_BY_TAX,
    STATUS_AWAITING_PARTNER,
    STATUS_AWAITING_US,
    STATUS_DRAFT,
    STATUS_REJECTED,
    STATUS_SIGNED,
)


class _Row:
    """Enough of `DidoxDocument` for the pure paths."""

    def __init__(self, *, status: int = STATUS_DRAFT, didox_id: str | None = "8ca0") -> None:
        self.id = 1
        self.didox_id = didox_id
        self.status = status
        self.status_synced_at = None
        self.owner_company_id = 7
        self.doc_type = "007"
        self.subject_kind = "contract"
        self.subject_id = 99
        self.provider_archive_path = None
        self.provider_archive_sha256 = None
        self.archived_at = None
        self.last_error = None


class _Db:
    def flush(self) -> None:
        pass

    def get(self, model: object, pk: object) -> None:
        return None


class _Redis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)


# ── the bytes to sign ─────────────────────────────────────────────────────────


class TestToSignBytes:
    def test_serialisation_is_compact_and_not_ascii_escaped(self) -> None:
        """Both properties matter: the module signs these bytes and Didox verifies
        against its own copy, so any reformatting breaks the match. Cyrillic
        escaped to `\\uXXXX` would be a different string entirely."""
        encoded = edi_service.to_sign_bytes({"a": 1, "b": "Полиэтилен"})
        decoded = base64.b64decode(encoded).decode("utf-8")

        assert decoded == '{"a":1,"b":"Полиэтилен"}'
        assert ", " not in decoded
        assert "\\u" not in decoded

    def test_it_round_trips_through_json(self) -> None:
        payload = {"contractdoc": {"contractno": "PI-1"}, "products": [{"count": "1000"}]}
        decoded = json.loads(base64.b64decode(edi_service.to_sign_bytes(payload)))
        assert decoded == payload


# ── the single-use stash ──────────────────────────────────────────────────────


class TestSignPayloadStash:
    def test_the_stash_is_consumed_by_the_first_read(self) -> None:
        redis_client = _Redis()
        key = "didox:signpayload:1:7"
        redis_client.values[key] = "DATA"

        assert edi_service._take_stashed_payload(redis_client, 1, 7) == "DATA"
        with pytest.raises(edi_service.SignPayloadExpired):
            edi_service._take_stashed_payload(redis_client, 1, 7)

    def test_a_missing_stash_is_an_expiry(self) -> None:
        with pytest.raises(edi_service.SignPayloadExpired):
            edi_service._take_stashed_payload(_Redis(), 1, 7)

    def test_no_redis_at_all_is_also_an_expiry_not_a_free_pass(self) -> None:
        """Degrading to "sign whatever you like" would drop the single-use
        guarantee exactly when the cache is unavailable."""
        with pytest.raises(edi_service.SignPayloadExpired):
            edi_service._take_stashed_payload(None, 1, 7)


# ── status application ────────────────────────────────────────────────────────


class _Client:
    def __init__(self) -> None:
        self.archive_calls = 0

    def archive(self, didox_id: str, *, user_key: str | None = None) -> bytes:
        self.archive_calls += 1
        return b"PK\x03\x04"


class TestApplyStatus:
    def test_status_moves_forward(self) -> None:
        row, client = _Row(status=STATUS_DRAFT), _Client()
        edi_service.apply_status(_Db(), row, STATUS_AWAITING_PARTNER, user_key="k", client=client)
        assert row.status == STATUS_AWAITING_PARTNER

    def test_a_stale_status_is_ignored(self) -> None:
        """The poll cursor is day-granular and overlapped on purpose, so pages
        repeat. Applying an older status would un-sign a signed document."""
        row, client = _Row(status=STATUS_SIGNED), _Client()
        edi_service.apply_status(_Db(), row, STATUS_AWAITING_PARTNER, user_key="k", client=client)
        assert row.status == STATUS_SIGNED

    def test_none_is_ignored(self) -> None:
        row, client = _Row(status=STATUS_AWAITING_PARTNER), _Client()
        edi_service.apply_status(_Db(), row, None, user_key="k", client=client)
        assert row.status == STATUS_AWAITING_PARTNER

    def test_rejected_records_but_activates_nothing(self) -> None:
        row, client = _Row(), _Client()
        activated = edi_service.apply_status(
            _Db(), row, STATUS_REJECTED, user_key="k", client=client
        )
        assert row.status == STATUS_REJECTED
        assert activated is False
        assert client.archive_calls == 0

    def test_annulled_by_the_tax_committee_changes_no_state_of_ours(self) -> None:
        """`50` is a legal event for a human. `active` is terminal and a deal may
        already be riding on it, so a silent new terminal state would leave that
        deal without footing."""
        row, client = _Row(), _Client()
        activated = edi_service.apply_status(
            _Db(), row, STATUS_ANNULLED_BY_TAX, user_key="k", client=client
        )
        assert row.status == STATUS_ANNULLED_BY_TAX
        assert activated is False
        assert client.archive_calls == 0

    def test_the_archive_is_fetched_exactly_once(self, monkeypatch) -> None:  # noqa: ANN001
        """It is the legal artefact and it is hashed; a second download could
        differ without anyone noticing."""
        monkeypatch.setattr(
            edi_service.storage_service,
            "store_didox_archive",
            lambda didox_id, blob: ("evidence/didox/x/archive.zip", "sha"),
        )
        row, client = _Row(), _Client()

        edi_service.apply_status(_Db(), row, STATUS_SIGNED, user_key="k", client=client)
        assert client.archive_calls == 1
        assert row.provider_archive_sha256 == "sha"

        # A repeat delivery (the outbox is at-least-once) must not re-fetch.
        row.status = STATUS_AWAITING_PARTNER
        edi_service.apply_status(_Db(), row, STATUS_SIGNED, user_key="k", client=client)
        assert client.archive_calls == 1

    def test_a_failed_archive_does_not_block_the_signed_transition(
        self, monkeypatch  # noqa: ANN001
    ) -> None:
        """The document IS signed either way, and the archive can be fetched
        again later. Losing the transition over evidence would be worse."""

        def _boom(didox_id: str, *, user_key: str | None = None) -> bytes:
            raise RuntimeError("s3 down")

        client = _Client()
        monkeypatch.setattr(client, "archive", _boom)
        row = _Row()

        edi_service.apply_status(_Db(), row, STATUS_SIGNED, user_key="k", client=client)
        assert row.status == STATUS_SIGNED
        assert row.provider_archive_sha256 is None


# ── numbering ─────────────────────────────────────────────────────────────────


class TestNumbering:
    def test_the_contract_number_prefers_the_deal_number(self) -> None:
        """The humans already use it in chat, documents and the escrow row; a
        second identifier for one transaction is a support ticket waiting."""
        from app.domains.edi.numbering import contract_number  # noqa: PLC0415

        assert (
            contract_number(deal_number="DEAL-2026-000125", contract_public_id="7b520eb7-86a9")
            == "DEAL-2026-000125"
        )

    def test_a_contract_with_no_deal_falls_back_to_its_public_id(self) -> None:
        from app.domains.edi.numbering import contract_number  # noqa: PLC0415

        assert contract_number(deal_number=None, contract_public_id="7b520eb7-86a9") == "C-7b520eb7"

    def test_no_two_advisory_lock_bases_collide_for_any_plausible_year(self) -> None:
        """Every yearly base is used as `BASE + year`, so what has to hold is that
        those key spaces stay disjoint over the years anyone will run this — not
        that the bases are far apart in the abstract.

        `LOCK_BASE_REQUEST` is excluded: it keys on `YYYYMMDD`, not a year, which
        its own comment says and which puts it in a different space entirely.
        """
        from app.core import numbering  # noqa: PLC0415

        bases = {
            name: value
            for name, value in vars(numbering).items()
            if name.startswith("LOCK_BASE_") and name != "LOCK_BASE_REQUEST"
        }
        assert "LOCK_BASE_ESF" in bases and "LOCK_BASE_SAMPLE_LETTER" in bases

        seen: dict[int, str] = {}
        for name, base in bases.items():
            for year in range(2020, 2101):
                key = base + year
                clash = seen.get(key)
                assert clash is None, f"{name} and {clash} share advisory key {key}"
                seen[key] = name


# ── which door a signature leaves by ──────────────────────────────────────────


class _SigningClient(_Client):
    """Records which endpoint the service reached for."""

    def __init__(self, *, status_after: int = STATUS_AWAITING_PARTNER) -> None:
        super().__init__()
        self.calls: list[str] = []
        self._status_after = status_after

    def timestamp(self, pkcs7_64: str, signature_hex: str, *, user_key: str | None = None) -> str:
        self.calls.append("timestamp")
        return "STAMPED"

    def join_signatures(self, s1: str, s2: str, *, user_key: str | None = None) -> str:
        self.calls.append("join")
        return "JOINED"

    def send_document(self, didox_id: str, signature: str, *, user_key: str | None = None):  # noqa: ANN201
        self.calls.append("send")
        return SimpleNamespace(ok=True, warning=None)

    def sign_document(self, didox_id: str, signature: str, *, user_key: str | None = None):  # noqa: ANN201
        self.calls.append("sign")
        return SimpleNamespace(ok=True, warning=None)

    def get_document(self, didox_id: str, *, owner: int = 1, user_key: str | None = None):  # noqa: ANN201
        self.calls.append(f"get(owner={owner})")
        return SimpleNamespace(status=self._status_after, to_sign="THEIRS", json_payload={})


class TestSubmitSignatureRouting:
    """Both directions leave by `POST /{id}/sign`; only the JOIN differs.

    On 21.08 `/sign` answered 500 `Undefined variable $isDraft` and we routed
    outgoing drafts through `PUT /{id}/send` instead. On 25.08, once the company
    had signed Didox's public offer, that 500 vanished — `/sign` began validating
    the signature properly — and `/send` started refusing a 007 with
    «Неподдерживаемый тип документа». The PHP error was a symptom of the unsigned
    offer, not a second door.
    """

    def _submit(self, row, client, *, company_id: int):  # noqa: ANN001, ANN202
        redis_client = _Redis()
        redis_client.setex(
            edi_service._SIGN_PAYLOAD_KEY.format(doc_id=row.id, company_id=company_id), 300, "DATA"
        )
        return edi_service.submit_signature(
            _Db(),
            redis_client,
            row,
            company_id=company_id,
            tax_id="312616547",
            pkcs7_64="P",
            signature_hex="H",
            user_key="k",
            client=client,
        )

    def test_our_own_draft_is_signed_without_joining(self, monkeypatch) -> None:  # noqa: ANN001
        """Nothing to join: the counterparty has not signed our draft yet."""
        monkeypatch.setattr(edi_service.onboarding, "assert_live", lambda: None)
        row, client = _Row(status=STATUS_DRAFT), _SigningClient()
        self._submit(row, client, company_id=row.owner_company_id)
        assert "sign" in client.calls
        assert "join" not in client.calls
        assert "send" not in client.calls

    def test_an_incoming_document_is_signed_after_joining_theirs(self, monkeypatch) -> None:  # noqa: ANN001
        """Accepting someone else's document is a different act from sending our
        own, and it is the one `/sign` is for — after their signature is joined
        first, or the tax committee refuses the pair."""
        monkeypatch.setattr(edi_service.onboarding, "assert_live", lambda: None)
        row, client = _Row(status=STATUS_AWAITING_US), _SigningClient(status_after=STATUS_SIGNED)
        self._submit(row, client, company_id=row.owner_company_id + 1)
        assert client.calls.index("join") < client.calls.index("sign")
