"""Presigned download URLs must name a host the client's browser can resolve.

`S3_ENDPOINT` is the INTERNAL address of the object store — `http://minio:9000`
under compose, where MinIO publishes no host ports at all. Every `presign_*` helper
signed against it, so the eleven document-download call sites (verification
documents, contract PDFs and bundles, deal attachments, lab letters, thread files,
registry evidence) handed out URLs that resolve only inside the docker network. The
images had been given a byte-proxy years earlier and a comment explaining exactly
this; the documents were never given anything.

The fix is a SECOND boto3 client, not a rewrite of the returned string, and that is
the part worth pinning: SigV4 lists `host` in `X-Amz-SignedHeaders`, so the host is
covered by the signature. Swapping it afterwards yields a URL the object store
answers 403 to — a fix that looks right in a diff and fails on every download.
"""

from __future__ import annotations

import ast
import pathlib
import re
import urllib.parse

import pytest

from app.core import storage
from app.core.config import settings


class TestPresignClientEndpoint:
    def test_public_endpoint_defaults_empty(self) -> None:
        """An unset value must change nothing for existing deployments."""
        assert settings.S3_PUBLIC_ENDPOINT == ""

    def test_presign_client_uses_the_public_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "S3_ENDPOINT", "http://minio:9000")
        monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT", "https://api.example.com")

        client = storage.get_s3_presign_client()

        assert client.meta.endpoint_url == "https://api.example.com"  # type: ignore[attr-defined]

    def test_presign_client_falls_back_to_the_internal_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty → old behaviour exactly, so this cannot break a deployment that
        has not been told about the new variable."""
        monkeypatch.setattr(settings, "S3_ENDPOINT", "http://minio:9000")
        monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT", "")

        client = storage.get_s3_presign_client()

        assert client.meta.endpoint_url == "http://minio:9000"  # type: ignore[attr-defined]

    def test_io_client_never_uses_the_public_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reads and writes stay on the internal network.

        The public endpoint goes through nginx and out over the internet; routing
        every `put_object` through it would be slower, would depend on the front
        door being up, and on the behind-proxy topology would loop back in.
        """
        monkeypatch.setattr(settings, "S3_ENDPOINT", "http://minio:9000")
        monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT", "https://api.example.com")

        client = storage.get_s3_client()

        assert client.meta.endpoint_url == "http://minio:9000"  # type: ignore[attr-defined]


class TestSignedUrlShape:
    """The URL nginx has to serve, checked against what boto3 actually emits.

    `location /polymer-files/` in the four nginx configs is a claim about this
    shape: bucket-first path, public host, no extra prefix. If boto3 ever produced
    something else the nginx location would silently stop matching and every
    download would 404.
    """

    def test_host_is_public_and_path_starts_with_the_bucket(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT", "https://api.example.com")
        monkeypatch.setattr(settings, "S3_BUCKET", "polymer-files")

        client = storage.get_s3_presign_client()
        url = client.generate_presigned_url(  # type: ignore[attr-defined]
            "get_object",
            Params={"Bucket": "polymer-files", "Key": "contracts/abc/contract_v1.pdf"},
            ExpiresIn=600,
        )

        parts = urllib.parse.urlparse(str(url))
        assert parts.netloc == "api.example.com"
        assert parts.path == "/polymer-files/contracts/abc/contract_v1.pdf"
        assert "X-Amz-Signature=" in parts.query

    def test_signs_with_sigv4_and_covers_the_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SigV4, pinned — and `host` among its signed headers.

        Botocore emits SigV2 here if left alone (`AWSAccessKeyId`/`Signature`/
        `Expires`), which does NOT sign the host: that URL is valid against any
        host that can reach the bucket. V4 binds it to the one it was signed for,
        which is what makes `proxy_set_header Host $host` in the nginx bucket
        location load-bearing — drop that line under v4 and MinIO answers 403
        SignatureDoesNotMatch. Both behaviours were checked against a real MinIO.
        """
        monkeypatch.setattr(settings, "S3_PUBLIC_ENDPOINT", "https://api.example.com")

        client = storage.get_s3_presign_client()
        url = client.generate_presigned_url(  # type: ignore[attr-defined]
            "get_object",
            Params={"Bucket": "polymer-files", "Key": "k"},
            ExpiresIn=600,
        )

        query = urllib.parse.parse_qs(urllib.parse.urlparse(str(url)).query)
        assert "AWS4-HMAC-SHA256" in query["X-Amz-Algorithm"], "fell back to SigV2"
        assert "host" in query["X-Amz-SignedHeaders"][0]


def test_every_presign_helper_signs_with_the_presign_client() -> None:
    """A new `presign_*` written against `s3_client` would reintroduce the bug.

    Source-level rather than behavioural on purpose: a call-site test only covers
    the helpers that exist today, and the failure mode here is somebody adding a
    twelfth download route next year by copying one of the three.
    """
    path = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "storage_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    offenders: list[str] = []
    checked: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("presign_"):
            continue
        body = ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""
        if "generate_presigned_url" not in body:
            continue  # the company logo/cover helpers return proxy paths, not signatures
        checked.append(node.name)
        if not re.search(r"\bs3_presign_client\b", body):
            offenders.append(f"{node.name} (line {node.lineno})")

    assert checked, "found no presigning helpers — has storage_service been restructured?"
    assert not offenders, (
        "these presign helpers sign with the INTERNAL client, so the URLs they "
        "return are unreachable outside the docker network: " + ", ".join(offenders)
    )
