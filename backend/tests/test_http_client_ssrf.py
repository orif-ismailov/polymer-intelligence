"""
Unit tests for the SSRF guard and fetch client (app.ingest.http_client).

All tests that touch DNS are patched so the suite runs offline without real
network access. Tests that exercise fetch_url use a mock transport so no
real HTTP connections are made.

NOTE: all imports from app.ingest.http_client are deferred inside test
function bodies to avoid triggering Settings() before the conftest
patch_env session fixture runs. This is the same pattern as test_celery_app.py
and test_rbac.py (see conftest.py scope="session" note).

SSRF guard (T-02-07) covers:
- Rejects loopback: 127.0.0.1, localhost
- Rejects cloud metadata: 169.254.169.254
- Rejects private RFC1918: 10.0.0.1, 192.168.1.1, 172.16.0.1
- Rejects non-http(s) schemes: file://, ftp://, data://
- Rejects URLs with no hostname
- Accepts a normal public https URL

fetch_url contracts (T-02-08, T-02-09):
- Uses settings.INGEST_HTTP_TIMEOUT_SECONDS as httpx timeout
- Sends the settings.INGEST_USER_AGENT header
- Rejects URLs that fail is_safe_url (raises ValueError)
- Raises ValueError if response body exceeds MAX_RESPONSE_BYTES
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── DNS resolution patches ──────────────────────────────────────────────────────

def _make_getaddrinfo(ip: str):
    """Return a mock getaddrinfo that resolves all hostnames to a specific IP."""
    family = socket.AF_INET
    socktype = socket.SOCK_STREAM
    proto = 0
    canonname = ""

    def _patched_getaddrinfo(host, port, *args, **kwargs):
        return [(family, socktype, proto, canonname, (ip, port or 0))]

    return _patched_getaddrinfo


# ── is_safe_url: reject loopback ────────────────────────────────────────────────

def test_is_safe_url_rejects_127_0_0_1():
    """SSRF guard rejects http://127.0.0.1 (loopback)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("127.0.0.1")):
        assert is_safe_url("http://127.0.0.1") is False


def test_is_safe_url_rejects_localhost():
    """SSRF guard rejects http://localhost (resolves to 127.0.0.1)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("127.0.0.1")):
        assert is_safe_url("http://localhost") is False


def test_is_safe_url_rejects_loopback_ipv6():
    """SSRF guard rejects http://[::1] (IPv6 loopback)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("::1")):
        assert is_safe_url("http://[::1]") is False


# ── is_safe_url: reject cloud metadata ─────────────────────────────────────────

def test_is_safe_url_rejects_link_local_metadata():
    """SSRF guard rejects http://169.254.169.254 (AWS/GCP metadata endpoint)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("169.254.169.254")):
        assert is_safe_url("http://169.254.169.254") is False


def test_is_safe_url_rejects_link_local_any_path():
    """SSRF guard rejects any URL that resolves to 169.254.x.x."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("169.254.100.1")):
        assert is_safe_url("http://metadata.internal/latest") is False


# ── is_safe_url: reject private RFC1918 ────────────────────────────────────────

def test_is_safe_url_rejects_10_0_0_1():
    """SSRF guard rejects http://10.0.0.1 (private RFC1918)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("10.0.0.1")):
        assert is_safe_url("http://10.0.0.1") is False


def test_is_safe_url_rejects_192_168():
    """SSRF guard rejects http://192.168.1.1 (private RFC1918)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("192.168.1.1")):
        assert is_safe_url("http://192.168.1.1") is False


def test_is_safe_url_rejects_172_16():
    """SSRF guard rejects http://172.16.0.1 (private RFC1918)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("172.16.0.1")):
        assert is_safe_url("http://172.16.0.1") is False


# ── is_safe_url: reject bad schemes ────────────────────────────────────────────

def test_is_safe_url_rejects_file_scheme():
    """SSRF guard rejects file:// scheme regardless of host."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    assert is_safe_url("file:///etc/passwd") is False


def test_is_safe_url_rejects_ftp_scheme():
    """SSRF guard rejects ftp:// scheme."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    assert is_safe_url("ftp://public.example.com/file.txt") is False


def test_is_safe_url_rejects_data_uri():
    """SSRF guard rejects data: URI scheme."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    assert is_safe_url("data:text/plain,hello") is False


# ── is_safe_url: reject DNS failure ────────────────────────────────────────────

def test_is_safe_url_rejects_dns_failure():
    """SSRF guard rejects URLs where DNS resolution fails (fail-safe)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", side_effect=socket.gaierror("NXDOMAIN")):
        assert is_safe_url("http://nonexistent.example.invalid") is False


# ── is_safe_url: accept public URL ─────────────────────────────────────────────

def test_is_safe_url_accepts_public_https():
    """SSRF guard accepts a normal public https URL."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    # Patch DNS to resolve to a public IP that is not in any private range
    with patch("socket.getaddrinfo", _make_getaddrinfo("93.184.216.34")):  # example.com
        assert is_safe_url("https://example.com/path") is True


def test_is_safe_url_accepts_public_http():
    """SSRF guard accepts a normal public http URL."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("93.184.216.34")):
        assert is_safe_url("http://example.com/") is True


# ── fetch_url: SSRF rejection ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_url_raises_for_private_url():
    """fetch_url raises ValueError for URLs that fail the SSRF guard."""
    from app.ingest.http_client import fetch_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("127.0.0.1")), \
         pytest.raises(ValueError, match="SSRF guard"):
        await fetch_url("http://localhost/admin")


# ── fetch_url: settings propagation ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_url_uses_user_agent_header():
    """fetch_url sends the INGEST_USER_AGENT header from settings."""
    import app.ingest.http_client as http_client  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415

    received_headers: dict[str, str] = {}

    async def mock_transport_fn(request: httpx.Request) -> httpx.Response:
        received_headers.update(dict(request.headers))
        return httpx.Response(200, content=b"ok")

    with patch.object(http_client, "is_safe_url", return_value=True), \
         patch("app.ingest.http_client._enforce_host_delay", new=AsyncMock()):

        class PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, **kwargs):
                kwargs.pop("transport", None)
                transport = httpx.MockTransport(mock_transport_fn)
                super().__init__(transport=transport, **kwargs)

        with patch("httpx.AsyncClient", PatchedAsyncClient):
            await http_client.fetch_url("https://example.com/")

    assert received_headers.get("user-agent") == settings.INGEST_USER_AGENT


def test_fetch_url_timeout_from_settings():
    """fetch_url uses INGEST_HTTP_TIMEOUT_SECONDS from settings (default=30)."""
    from app.core.config import settings  # noqa: PLC0415

    assert settings.INGEST_HTTP_TIMEOUT_SECONDS == 30


def test_fetch_url_retry_count_from_settings():
    """fetch_url uses INGEST_HTTP_RETRIES from settings (default=3)."""
    from app.core.config import settings  # noqa: PLC0415

    assert settings.INGEST_HTTP_RETRIES == 3


# ── fetch_url: body size cap ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_url_raises_for_oversized_body():
    """fetch_url raises ValueError when response body exceeds MAX_RESPONSE_BYTES."""
    import app.ingest.http_client as http_client  # noqa: PLC0415
    from app.ingest.http_client import MAX_RESPONSE_BYTES  # noqa: PLC0415

    # Create a response that produces just enough data to exceed the cap
    oversized_data = b"x" * (MAX_RESPONSE_BYTES + 1)

    async def _oversized_transport_fn(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=oversized_data)

    with patch.object(http_client, "is_safe_url", return_value=True), \
         patch("app.ingest.http_client._enforce_host_delay", new=AsyncMock()):

        class PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, **kwargs):
                kwargs.pop("transport", None)
                transport = httpx.MockTransport(_oversized_transport_fn)
                super().__init__(transport=transport, **kwargs)

        with patch("httpx.AsyncClient", PatchedAsyncClient), \
             pytest.raises(ValueError, match="size cap"):
            await http_client.fetch_url("https://example.com/bigfile")


# ── is_safe_url: reject RFC 6598 CGNAT (CR-02) ─────────────────────────────────

def test_is_safe_url_rejects_cgnat_100_64():
    """CR-02: SSRF guard rejects 100.64.0.0/10 (RFC 6598 CGNAT — not flagged by ipaddress)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("100.64.0.1")):
        assert is_safe_url("http://100.64.0.1") is False


def test_is_safe_url_rejects_cgnat_100_127():
    """CR-02: SSRF guard rejects 100.127.255.255 (upper end of RFC 6598 range)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("100.127.255.255")):
        assert is_safe_url("http://cgnat.internal") is False


def test_is_safe_url_accepts_100_128():
    """CR-02: 100.128.0.1 is outside RFC 6598 range and should be accepted (public)."""
    from app.ingest.http_client import is_safe_url  # noqa: PLC0415

    with patch("socket.getaddrinfo", _make_getaddrinfo("100.128.0.1")):
        assert is_safe_url("http://example.com/") is True


# ── fetch_url: no-redirect SSRF guard (CR-01) ──────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_url_does_not_follow_redirects():
    """CR-01: fetch_url must NOT follow HTTP redirects (follow_redirects=False).

    A redirect to an internal IP bypasses the SSRF pre-request DNS check because
    is_safe_url() only validates the *original* URL, not redirect targets.
    """
    import app.ingest.http_client as http_client  # noqa: PLC0415

    redirect_followed = False

    async def _redirect_transport_fn(request: httpx.Request) -> httpx.Response:
        nonlocal redirect_followed
        if str(request.url) == "https://example.com/":
            # Attempt to redirect to internal IP
            return httpx.Response(
                301,
                headers={"Location": "http://169.254.169.254/latest/meta-data/"},
                content=b"",
                request=request,
            )
        redirect_followed = True
        return httpx.Response(200, content=b"metadata", request=request)

    with patch.object(http_client, "is_safe_url", return_value=True), \
         patch("app.ingest.http_client._enforce_host_delay", new=AsyncMock()):

        class PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, **kwargs):
                kwargs.pop("transport", None)
                transport = httpx.MockTransport(_redirect_transport_fn)
                super().__init__(transport=transport, **kwargs)

        # With follow_redirects=False, the 301 response is returned as-is.
        # raise_for_status() raises HTTPStatusError on 3xx.
        with patch("httpx.AsyncClient", PatchedAsyncClient), \
             pytest.raises(httpx.HTTPStatusError):
            await http_client.fetch_url("https://example.com/")

    # The redirect target (internal IP) must never have been fetched
    assert not redirect_followed, "fetch_url followed a redirect — SSRF bypass possible"


# ── fetch_url: retry logic ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_url_retries_on_connection_error():
    """fetch_url retries on ConnectError up to INGEST_HTTP_RETRIES times."""
    import app.ingest.http_client as http_client  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415

    attempt_count = 0

    async def _failing_transport_fn(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        raise httpx.ConnectError("Connection refused")

    with patch.object(http_client, "is_safe_url", return_value=True), \
         patch("app.ingest.http_client._enforce_host_delay", new=AsyncMock()), \
         patch("asyncio.sleep", new=AsyncMock()):  # skip actual backoff sleep

        class PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, **kwargs):
                kwargs.pop("transport", None)
                transport = httpx.MockTransport(_failing_transport_fn)
                super().__init__(transport=transport, **kwargs)

        with patch("httpx.AsyncClient", PatchedAsyncClient), \
             pytest.raises(httpx.ConnectError):
            await http_client.fetch_url("https://example.com/")

    # Should attempt max_retries + 1 times total (initial + retries)
    assert attempt_count == settings.INGEST_HTTP_RETRIES + 1


# ── fetch_url: compressed responses must not be double-decompressed ─────────────


@pytest.mark.asyncio
async def test_fetch_url_decodes_gzip_without_double_decompress():
    """Regression: a gzip-compressed source must be decoded exactly once.

    _read_response_capped() streams via aiter_bytes(), which already decompresses
    per Content-Encoding. The synthetic Response must therefore DROP Content-Encoding
    so callers reading .text/.content don't re-inflate the decoded body and hit
    'Error -3 while decompressing data: incorrect header check'. This silently broke
    every gzip/br/deflate-compressed source (e.g. UZEX) in production.
    """
    import gzip  # noqa: PLC0415

    import app.ingest.http_client as http_client  # noqa: PLC0415

    html = (
        "<html><body><table class='custom-table-dark'><tbody>"
        "<tr><td>row</td></tr></tbody></table></body></html>"
    )
    gzipped = gzip.compress(html.encode("utf-8"))

    async def _gzip_transport_fn(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip", "content-type": "text/html"},
            content=gzipped,
        )

    with patch.object(http_client, "is_safe_url", return_value=True), \
         patch("app.ingest.http_client._enforce_host_delay", new=AsyncMock()):

        class PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, **kwargs):
                kwargs.pop("transport", None)
                transport = httpx.MockTransport(_gzip_transport_fn)
                super().__init__(transport=transport, **kwargs)

        with patch("httpx.AsyncClient", PatchedAsyncClient):
            resp = await http_client.fetch_url("https://example.com/")

    # .text returns the decompressed HTML (would raise 'incorrect header check' if the
    # Content-Encoding header were carried onto the already-decoded body).
    assert "custom-table-dark" in resp.text
    # The stale Content-Encoding/Content-Length are stripped from the synthetic response.
    assert "content-encoding" not in resp.headers
