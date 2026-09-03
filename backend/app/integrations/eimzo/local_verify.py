"""DEV-ONLY structural verification of a REAL E-IMZO PKCS#7.

**This is not signature verification and must never reach production.** It reads
a genuine PKCS#7 produced by the E-IMZO desktop module — parsing the signer's
certificate and the content it covers — but it does NOT check the signature
bytes. It cannot: those are O'zDSt / GOST (digest OID `1.2.860.3.15.2.3.2.1.1`),
which no stock Python crypto library implements. Only the UNICON `e-imzo-server`
sidecar does that, and its image is a licensed artifact this repo cannot pull.

Why it exists anyway: `EIMZO_STUB` previously understood ONLY the synthetic JSON
envelope our test bridge emits, so signing with a real key on a developer machine
answered «Подпись недействительна» — a message that blames the user's key for a
limitation of the deployment. With this, a real token signs, the real certificate
subject reaches the database, and the whole registration rail is exercisable with
real data instead of a fixture.

What it DOES check:
  * the payload really is a PKCS#7/CMS SignedData that parses,
  * the embedded content equals the challenge we issued (replay binding),
  * the signer certificate is inside its validity window,
  * the organisation STIR is present (the caller matches it against the company).

What it does NOT check, and why each is a hole:
  * **the signature bytes** — anyone holding a public certificate could wrap our
    challenge in a forged envelope and pass,
  * **the trust chain** — `deploy/eimzo/truststore` is not consulted, so a
    `test.e-imzo.uz` TestRoot key is accepted exactly like a production one,
  * **revocation** — no OCSP, no CRL.

Those three are the whole reason `EIMZO_STUB` is now refused unless `DEBUG` is on
(`Settings.check_eimzo_stub_is_dev_only`).

The module emits BER with indefinite lengths (`30 80 …`), not strict DER, so the
parsing here is deliberately tolerant — `cryptography` warns and falls back for
the certificates, and the content walker handles constructed OCTET STRINGs.
"""

from __future__ import annotations

import datetime
import logging
import warnings

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs7 as crypto_pkcs7

# Safe at module scope: `client` imports THIS module lazily, inside the dispatch,
# so the edge only runs one way at import time.
from app.integrations.eimzo.client import EimzoSigner, EimzoVerifyResult

logger = logging.getLogger(__name__)

__all__ = ["looks_like_pkcs7", "verify_structural"]

# X.509 subject OIDs. The two `1.2.860.*` are Uzbekistan's national additions and
# are the only reason a certificate can identify a COMPANY rather than a person.
_OID_ORG_INN = "1.2.860.3.16.1.1"
_OID_PINFL = "1.2.860.3.16.1.2"
_OID_CN = "2.5.4.3"
_OID_ORG = "2.5.4.10"
_OID_TITLE = "2.5.4.12"

# ContentInfo.contentType = id-data (1.2.840.113549.1.7.1), DER-encoded.
_DATA_OID = bytes.fromhex("06092a864886f70d010701")

_TAG_OCTET_STRING = 0x04
_TAG_OCTET_STRING_CONSTRUCTED = 0x24
_TAG_CONTEXT_0 = 0xA0


def looks_like_pkcs7(payload: bytes) -> bool:
    """A cheap shape test: does this start like an ASN.1 SEQUENCE?

    Used only to decide which verifier a dev payload belongs to. The stub's own
    envelope is base64 JSON, so it begins `{`; a PKCS#7 begins `0x30`.
    """
    return bool(payload) and payload[0] == 0x30


def _read_length(buf: bytes, i: int) -> tuple[int | None, int]:
    """BER length at `i` → `(length, next_index)`; `None` length means indefinite."""
    first = buf[i]
    i += 1
    if first == 0x80:
        return None, i
    if first < 0x80:
        return first, i
    count = first & 0x7F
    return int.from_bytes(buf[i : i + count], "big"), i + count


def _collect_octets(buf: bytes, i: int) -> bytes | None:
    """Read an OCTET STRING at `i`, joining the chunks of a constructed one.

    The module emits `24 80 04 17 …` — a constructed, indefinite-length OCTET
    STRING wrapping primitive segments — so a reader that only understands the
    primitive form finds nothing.
    """
    if i >= len(buf):
        return None
    tag = buf[i]
    if tag == _TAG_OCTET_STRING:
        length, j = _read_length(buf, i + 1)
        if length is None:
            return None
        return buf[j : j + length]
    if tag != _TAG_OCTET_STRING_CONSTRUCTED:
        return None

    length, j = _read_length(buf, i + 1)
    end = len(buf) if length is None else j + length
    out = bytearray()
    while j < end - 1:
        if buf[j] == 0x00 and buf[j + 1] == 0x00:  # end-of-contents
            break
        if buf[j] != _TAG_OCTET_STRING:
            break
        chunk_len, k = _read_length(buf, j + 1)
        if chunk_len is None:
            break
        out += buf[k : k + chunk_len]
        j = k + chunk_len
    return bytes(out)


def _embedded_content(der: bytes) -> bytes | None:
    """The bytes the signature covers, or None when the envelope is detached.

    Located by finding `encapContentInfo.eContentType = id-data` and stepping
    into the `[0] EXPLICIT` that follows it. A full CMS decode would be tidier,
    but `pyasn1` refuses this BER outright and `pyasn1_modules` is not a
    dependency — for a dev-only reader, walking the two wrappers is enough.
    """
    idx = der.find(_DATA_OID)
    if idx < 0:
        return None
    i = idx + len(_DATA_OID)
    if i >= len(der) or der[i] != _TAG_CONTEXT_0:
        return None  # detached: no content to compare
    _, i = _read_length(der, i + 1)
    return _collect_octets(der, i)


def _attr(cert: x509.Certificate, oid: str) -> str | None:
    for attribute in cert.subject:
        if attribute.oid.dotted_string == oid:
            value = attribute.value
            return value if isinstance(value, str) else None
    return None


def _pick_signer_certificate(certs: list[x509.Certificate]) -> x509.Certificate | None:
    """The end-entity certificate among the chain the envelope carries.

    Order is not guaranteed, so this selects on meaning rather than position:
    only a person's certificate carries the organisation STIR, and a CA in the
    same bundle is the issuer of something else in it.
    """
    candidates = [c for c in certs if _attr(c, _OID_ORG_INN)]
    if not candidates:
        return None
    issuers = {c.issuer for c in certs}
    leaves = [c for c in candidates if c.subject not in issuers]
    return leaves[0] if leaves else candidates[0]


def verify_structural(pkcs7_b64: str, challenge: str, payload: bytes) -> EimzoVerifyResult:
    """Read a real PKCS#7 far enough to run the flow — WITHOUT checking the signature.

    `payload` is the already-decoded `pkcs7_b64`, so the caller's base64 work is
    not repeated. Every failure returns a result rather than raising: this sits
    where the sidecar would, and that contract answers verdicts, not exceptions.
    """
    try:
        with warnings.catch_warnings():
            # `cryptography` warns that it fell back from DER to BER. That fallback
            # is the ONLY reason this works — the module's output is indefinite-length
            # BER — so the warning is expected, not a defect to surface.
            warnings.simplefilter("ignore")
            certs = list(crypto_pkcs7.load_der_pkcs7_certificates(payload))
    except Exception as exc:  # noqa: BLE001 — any malformed envelope is one verdict
        logger.info("eimzo.local_verify.unparseable", extra={"error": str(exc)})
        return EimzoVerifyResult(ok=False, error="signature_invalid")

    cert = _pick_signer_certificate(certs)
    if cert is None:
        # A certificate with no org STIR is an INDIVIDUAL's key: real, valid, and
        # unable to register a company. Named separately so the cabinet can say so.
        return EimzoVerifyResult(ok=False, error="cert_no_tin")

    signer = EimzoSigner(
        org_name=_attr(cert, _OID_ORG),
        org_inn=_attr(cert, _OID_ORG_INN),
        full_name=_attr(cert, _OID_CN),
        pinfl=_attr(cert, _OID_PINFL),
        position=_attr(cert, _OID_TITLE),
        serial_number=format(cert.serial_number, "x"),
    )

    content = _embedded_content(payload)
    if content is None or content != challenge.encode("utf-8"):
        # The one property this verifier CAN establish: the envelope covers the
        # nonce we just issued, so it is not a replay of an older signature.
        return EimzoVerifyResult(ok=False, signer=signer, error="challenge_mismatch")

    now = datetime.datetime.now(datetime.UTC)
    if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
        return EimzoVerifyResult(ok=False, signer=signer, error="cert_expired")

    logger.warning(
        "eimzo.local_verify.accepted_without_crypto",
        extra={"org_inn": signer.org_inn, "serial": signer.serial_number},
    )
    return EimzoVerifyResult(ok=True, signer=signer, revoked=False)
