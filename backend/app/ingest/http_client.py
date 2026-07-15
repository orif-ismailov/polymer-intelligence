"""
Hardened httpx fetch client for all outbound data collection.

This is the SINGLE chokepoint for all external HTTP requests made by adapters.
All adapters MUST route outbound fetches through fetch_url() — never create
their own httpx client.

Security controls enforced here (T-02-07, T-02-08, T-02-09):
- SSRF guard: is_safe_url() rejects loopback/private/link-local/reserved IPs
  and non-http(s) schemes before any request is made (T-02-07)
- Timeout: configurable via settings.INGEST_HTTP_TIMEOUT_SECONDS (T-02-08)
- Retry with exponential backoff: up to settings.INGEST_HTTP_RETRIES (T-02-09)
- Per-host delay: ≥settings.INGEST_PER_HOST_DELAY_SECONDS between requests
  to the same host (T-02-09 robots-courtesy)
- Response body size cap: bodies over MAX_RESPONSE_BYTES are rejected without
  full buffering to prevent worker OOM (T-02-08)
- Honest User-Agent: settings.INGEST_USER_AGENT is always sent

Usage::

    from app.ingest.http_client import fetch_url, is_safe_url

    if not is_safe_url(url):
        raise ValueError(f"SSRF guard: {url!r} is not a safe target")
    response = await fetch_url(url)
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Maximum response body size (25 MB) — bodies over this are rejected without
# full buffering to prevent worker OOM (T-02-08).
MAX_RESPONSE_BYTES: int = 25 * 1024 * 1024  # 25 MB

# Allowed URL schemes for outbound fetches
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# Additional CIDR ranges not flagged by Python's ipaddress module but that must
# be blocked for SSRF protection (CR-02 / T-02-07):
#   - RFC 6598 CGNAT / shared address space (100.64.0.0/10) — Python 3.x does
#     NOT classify this as is_private, is_reserved, or any other blocked attr.
#     In cloud environments (AWS, GCP, Azure) internal load-balancers and VPC
#     endpoints can reside here, so an attacker-controlled endpoint_url could
#     reach internal services through this gap.
_SSRF_BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.IPv4Network("100.64.0.0/10"),  # RFC 6598 — CGNAT/shared address space
)

# Per-host request timestamps: host -> last request epoch time
# Used to enforce the per-host minimum delay between requests.
_host_last_request: dict[str, float] = {}
_host_last_request_lock = asyncio.Lock()


def is_safe_url(url: str) -> bool:
    """Return True if the URL is safe to fetch; False if it should be rejected.

    SSRF guard (T-02-07): rejects requests that could reach internal
    infrastructure, cloud metadata endpoints, or non-HTTP schemes:

    Rejected:
    - Non-http(s) schemes (file://, ftp://, data://, etc.)
    - Loopback addresses (127.0.0.0/8, ::1)
    - Private/RFC1918 networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local addresses (169.254.0.0/16 — cloud metadata; fe80::/10)
    - Reserved/unspecified addresses (0.0.0.0, ::/128, 240.0.0.0/4)
    - Hostnames that resolve to any of the above

    Accepted:
    - http(s) URLs with a hostname that resolves to a public routable IP

    Note: DNS resolution happens at validation time; if resolution fails,
    the URL is rejected (fail-safe for non-existent/private hostnames).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Reject non-http(s) schemes
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Resolve the hostname to check if it points to a private/reserved address
    try:
        # getaddrinfo returns all addresses for the hostname
        addr_infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, socket.herror, OSError):
        # DNS resolution failed — fail-safe: reject
        return False

    if not addr_infos:
        return False

    for addr_info in addr_infos:
        # addr_info = (family, type, proto, canonname, sockaddr)
        # sockaddr = (address, port) for IPv4 or (address, port, flow, scope) for IPv6
        sockaddr = addr_info[4]
        ip_str = sockaddr[0]

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            # Cannot parse address — reject
            return False

        if _is_private_ip(ip):
            return False

    return True


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP address should be blocked (SSRF guard).

    Blocks loopback, private, link-local, reserved addresses, and any range
    listed in _SSRF_BLOCKED_NETWORKS (e.g. RFC 6598 CGNAT — CR-02 / T-02-07).
    """
    if (
        ip.is_loopback          # 127.0.0.1, ::1
        or ip.is_private        # 10.x, 172.16-31.x, 192.168.x, fc00::/7
        or ip.is_link_local     # 169.254.x.x, fe80::/10 (cloud metadata)
        or ip.is_reserved       # 240.0.0.0/4, etc.
        or ip.is_unspecified    # 0.0.0.0, ::
        or ip.is_multicast      # 224.0.0.0/4, ff00::/8
    ):
        return True
    # Explicit check for ranges not covered by the standard ipaddress attributes
    # (e.g. RFC 6598 CGNAT 100.64.0.0/10 is not flagged by any standard attr)
    return any(ip in net for net in _SSRF_BLOCKED_NETWORKS)


async def fetch_url(
    url: str,
    *,
    method: str = "GET",
    json_body: dict[str, object] | None = None,
    host_delay: float | None = None,
) -> httpx.Response:
    """Fetch a URL using the hardened httpx client.

    Applies all security controls before and during the request:
    1. SSRF guard — raises ValueError if is_safe_url() returns False
    2. Per-host delay — waits to satisfy minimum inter-request delay
    3. HTTP request with timeout, retry+backoff, honest User-Agent
    4. Response body size cap — reads in chunks, raises ValueError if too large

    Args:
        url: The URL to fetch. Must pass is_safe_url() check.
        method: HTTP method (default "GET"). Pass "POST" for JSON-API sources such
            as the xarid procurement portal. Note: retries re-issue the request, so
            only use non-GET methods for idempotent/read-only endpoints (list/detail
            queries), never for mutations.
        json_body: Optional JSON body sent with the request (sets Content-Type:
            application/json). Ignored for GET when None.
        host_delay: Minimum seconds between requests to the same host.
            Defaults to settings.INGEST_PER_HOST_DELAY_SECONDS.

    Returns:
        An httpx.Response with the body already read (bytes in .content).

    Raises:
        ValueError: If the URL fails the SSRF guard or the response body
            exceeds MAX_RESPONSE_BYTES.
        httpx.HTTPError: On network/HTTP errors after all retries are exhausted.
        httpx.TimeoutException: If the request times out.
    """
    if host_delay is None:
        host_delay = settings.INGEST_PER_HOST_DELAY_SECONDS

    # SSRF guard — must come before any socket activity
    if not is_safe_url(url):
        raise ValueError(f"SSRF guard: refusing to fetch unsafe URL: {url!r}")

    # Extract hostname for per-host delay tracking
    hostname = urlparse(url).hostname or url

    # Enforce per-host minimum delay
    await _enforce_host_delay(hostname, host_delay)

    timeout = settings.INGEST_HTTP_TIMEOUT_SECONDS
    max_retries = settings.INGEST_HTTP_RETRIES
    user_agent = settings.INGEST_USER_AGENT

    headers = {"User-Agent": user_agent}
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        if attempt > 0:
            # Exponential backoff: 2s, 4s, 8s, ...
            backoff = 2.0 ** attempt
            logger.debug(
                "http_client.retry",
                extra={"url": url, "attempt": attempt, "backoff_s": backoff},
            )
            await asyncio.sleep(backoff)

        try:
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout),
                    # CR-01 / T-02-07: redirects are disabled to prevent SSRF bypass.
                    # An HTTP 3xx response to an internal IP would bypass is_safe_url()
                    # because the pre-request DNS check only validates the *original* URL.
                    # Trusted data sources should always use direct (non-redirecting) URLs.
                    follow_redirects=False,
                    headers=headers,
                ) as client,
                # Stream the response to enforce the body size cap without
                # buffering the full body into memory (T-02-08)
                client.stream(method, url, json=json_body) as response,
            ):
                    response.raise_for_status()
                    content = await _read_response_capped(response)

            # Record successful request time for per-host delay
            _host_last_request[hostname] = time.monotonic()

            # Build a synthetic Response with the capped content so callers
            # get a normal httpx.Response to work with.
            #
            # _read_response_capped() streams via aiter_bytes(), which ALREADY
            # decompresses per the response's Content-Encoding. Carrying the original
            # Content-Encoding onto the synthetic Response would make httpx try to
            # decompress the already-decoded body a SECOND time on .text/.content
            # ("Error -3 while decompressing data: incorrect header check") — breaking
            # every gzip/br/deflate-compressed source. Content-Length is likewise the
            # compressed length and no longer matches. Drop both so the decoded content
            # is served verbatim.
            clean_headers = httpx.Headers(response.headers)
            for _h in ("content-encoding", "content-length"):
                if _h in clean_headers:
                    del clean_headers[_h]

            return httpx.Response(
                status_code=response.status_code,
                headers=clean_headers,
                content=content,
                request=response.request,
            )

        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            logger.warning(
                "http_client.fetch_error",
                extra={"url": url, "attempt": attempt, "error": str(exc)},
            )
            if attempt == max_retries:
                break
            # Record attempt time even on error to respect per-host delay on retry
            _host_last_request[hostname] = time.monotonic()
            continue
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning(
                "http_client.http_error",
                extra={"url": url, "attempt": attempt, "error": str(exc)},
            )
            if attempt == max_retries:
                break
            _host_last_request[hostname] = time.monotonic()
            continue

    # All retries exhausted
    assert last_exc is not None
    raise last_exc


async def _enforce_host_delay(hostname: str, host_delay: float) -> None:
    """Sleep if needed to satisfy the minimum per-host inter-request delay.

    Uses an asyncio.Lock to serialize delay checks across concurrent coroutines
    that might fetch from the same host simultaneously.
    """
    if host_delay <= 0:
        return

    async with _host_last_request_lock:
        last = _host_last_request.get(hostname)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < host_delay:
                wait = host_delay - elapsed
                await asyncio.sleep(wait)
        # Mark this host as "being requested now" before releasing the lock
        _host_last_request[hostname] = time.monotonic()


async def _read_response_capped(response: httpx.Response) -> bytes:
    """Read a streaming response, raising ValueError if it exceeds MAX_RESPONSE_BYTES.

    Reads in chunks without buffering the full body to prevent OOM on oversized
    responses from untrusted sources (T-02-08).

    Args:
        response: An httpx.Response in streaming mode (inside `async with client.stream()`).

    Returns:
        The response body as bytes.

    Raises:
        ValueError: If the accumulated body exceeds MAX_RESPONSE_BYTES.
    """
    chunks: list[bytes] = []
    total = 0

    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):  # 64 KB chunks
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ValueError(
                f"Response body from {response.url!r} exceeds the "
                f"{MAX_RESPONSE_BYTES // (1024 * 1024)} MB size cap — "
                "request aborted to prevent worker OOM (T-02-08)"
            )
        chunks.append(chunk)

    return b"".join(chunks)
