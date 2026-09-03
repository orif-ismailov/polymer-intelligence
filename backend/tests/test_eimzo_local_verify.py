"""Unit tests for the DEV-only structural PKCS#7 reader (`eimzo/local_verify.py`).

Every certificate here is generated in-process. A real E-IMZO certificate carries
a live PINFL — personal data this repo masks everywhere else — so it must never
become a committed fixture, and none of these tests needs one: what they exercise
is the parsing, the OID extraction and the challenge binding, all of which a
synthetic certificate reproduces exactly.

The one shape a synthetic fixture CANNOT reproduce is the module's indefinite-length
BER (`24 80 04 17 … 00 00`), because `cryptography` emits strict DER — so the
constructed-OCTET-STRING walker is covered directly, with the byte pattern the
real module produced.
"""

from __future__ import annotations

import base64
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7 as crypto_pkcs7
from cryptography.x509.oid import NameOID

from app.integrations.eimzo import local_verify

_ORG_INN = x509.ObjectIdentifier("1.2.860.3.16.1.1")
_PINFL = x509.ObjectIdentifier("1.2.860.3.16.1.2")


def _signed(
    challenge: str = "chal-123",
    *,
    org_inn: str | None = "301234567",
    valid_days: tuple[int, int] = (-1, 30),
) -> bytes:
    """A genuine PKCS#7 over `challenge`, signed with RSA.

    RSA rather than O'zDSt on purpose: the verifier under test does NOT check the
    signature bytes, so the algorithm is irrelevant to it — and that is precisely
    the property these tests should make visible.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [
        x509.NameAttribute(NameOID.COMMON_NAME, "TEST HOLDER"),
        x509.NameAttribute(_PINFL, "31234567890123"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OOO SYNTHETIC"),
        x509.NameAttribute(NameOID.TITLE, "Director"),
    ]
    if org_inn is not None:
        attrs.append(x509.NameAttribute(_ORG_INN, org_inn))
    name = x509.Name(attrs)
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(0xABCDEF)
        .not_valid_before(now + datetime.timedelta(days=valid_days[0]))
        .not_valid_after(now + datetime.timedelta(days=valid_days[1]))
        .sign(key, hashes.SHA256())
    )
    return (
        crypto_pkcs7.PKCS7SignatureBuilder()
        .set_data(challenge.encode("utf-8"))
        .add_signer(cert, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [])
    )


class TestShapeDetection:
    def test_asn1_is_recognised_and_json_is_not(self) -> None:
        assert local_verify.looks_like_pkcs7(_signed()) is True
        assert local_verify.looks_like_pkcs7(b'{"challenge": "x"}') is False
        assert local_verify.looks_like_pkcs7(b"") is False


class TestStructuralVerification:
    def test_the_national_oids_reach_the_signer(self) -> None:
        payload = _signed("chal-123")
        result = local_verify.verify_structural("", "chal-123", payload)
        assert result.ok is True
        assert result.signer.org_inn == "301234567"
        assert result.signer.pinfl == "31234567890123"
        assert result.signer.full_name == "TEST HOLDER"
        assert result.signer.org_name == "OOO SYNTHETIC"
        assert result.signer.position == "Director"
        assert result.signer.serial_number == "abcdef"

    def test_the_content_must_cover_the_issued_challenge(self) -> None:
        """The one property this verifier can actually establish: no replay."""
        payload = _signed("chal-123")
        result = local_verify.verify_structural("", "a-different-nonce", payload)
        assert result.ok is False
        assert result.error == "challenge_mismatch"
        # The signer is still reported, so the failure can be attributed.
        assert result.signer.org_inn == "301234567"

    def test_a_key_without_an_org_stir_is_an_individual(self) -> None:
        """type=0 keys are real and valid — they just cannot register a company."""
        payload = _signed("chal-123", org_inn=None)
        result = local_verify.verify_structural("", "chal-123", payload)
        assert result.ok is False
        assert result.error == "cert_no_tin"

    def test_an_expired_certificate_is_refused(self) -> None:
        payload = _signed("chal-123", valid_days=(-40, -10))
        result = local_verify.verify_structural("", "chal-123", payload)
        assert result.ok is False
        assert result.error == "cert_expired"

    @pytest.mark.parametrize("blob", [b"\x30\x00", b"\x30\x82\xff\xffnot-asn1", b"\x30"])
    def test_malformed_envelopes_are_one_verdict_not_an_exception(self, blob: bytes) -> None:
        """This sits where the sidecar would, and that contract answers verdicts."""
        result = local_verify.verify_structural("", "chal-123", blob)
        assert result.ok is False
        assert result.error in {"signature_invalid", "cert_no_tin"}


class TestIndefiniteLengthBer:
    """The shape `cryptography` will not emit but the desktop module always does."""

    def test_constructed_octet_string_chunks_are_joined(self) -> None:
        # 24 80 (constructed, indefinite) { 04 03 "abc", 04 03 "def" } 00 00
        ber = bytes.fromhex("248004036162630403646566") + b"\x00\x00"
        assert local_verify._collect_octets(ber, 0) == b"abcdef"

    def test_primitive_octet_string_is_read_directly(self) -> None:
        assert local_verify._collect_octets(bytes.fromhex("0403616263"), 0) == b"abc"

    def test_the_modules_real_wrapper_shape_yields_the_challenge(self) -> None:
        """Exactly the bytes observed from E-IMZO v6.4.7: id-data, [0], 24 80, 04 17."""
        challenge = b"dev-verifier-sample-001"
        der = (
            bytes.fromhex("06092a864886f70d010701")  # id-data
            + b"\xa0\x80"  # [0] EXPLICIT, indefinite
            + b"\x24\x80"  # constructed OCTET STRING, indefinite
            + bytes([0x04, len(challenge)])
            + challenge
            + b"\x00\x00"
        )
        assert local_verify._embedded_content(der) == challenge

    def test_a_detached_envelope_has_no_content(self) -> None:
        der = bytes.fromhex("06092a864886f70d010701") + b"\x31\x00"  # no [0] wrapper
        assert local_verify._embedded_content(der) is None


class TestStubDispatch:
    """`_stub_verify` must keep serving BOTH developer payload shapes."""

    def test_the_synthetic_json_envelope_still_verifies(self) -> None:
        """CI and every e2e spec depend on this branch — it must not regress."""
        import json

        from app.integrations.eimzo.client import _stub_verify

        blob = base64.b64encode(
            json.dumps({"challenge": "chal-123", "tin": "301234567", "name": "IVANOV"}).encode()
        ).decode()
        result = _stub_verify(blob, "chal-123")
        assert result.ok is True
        assert result.signer.org_inn == "301234567"

    def test_a_real_pkcs7_reaches_the_structural_verifier(self) -> None:
        """The regression this whole module exists for: a real key used to be
        told «подпись недействительна» because only JSON was understood."""
        from app.integrations.eimzo.client import _stub_verify

        blob = base64.b64encode(_signed("chal-123")).decode()
        result = _stub_verify(blob, "chal-123")
        assert result.ok is True
        assert result.signer.org_inn == "301234567"

    def test_neither_shape_is_still_invalid(self) -> None:
        from app.integrations.eimzo.client import _stub_verify

        assert _stub_verify(base64.b64encode(b"plain text").decode(), "c").error == (
            "signature_invalid"
        )
