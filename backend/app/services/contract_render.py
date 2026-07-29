"""Contract document rendering (R3 Stage B — TB1.3).

`render_contract_html` is a **pure, deterministic** function: template HTML +
variables + both companies' requisites → filled HTML (timestamps are an injected
variable, never `now()`), so the golden test can pin a stable sha256. `html_to_pdf`
is the only impure part — WeasyPrint (national fonts frozen in the backend image);
its import is lazy so the module loads without the native libs present (they're in
the Docker image / dev machine, not necessarily CI).

Security (TB4.3): the caller decrypts bank accounts only here, inside the render
path — full requisites ARE required in a real contract; they never leave this seam
except inside the generated document, which is member/staff-gated.
"""

from __future__ import annotations

import html
import re

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _fill(template_html: str, context: dict[str, str]) -> str:
    """Substitute `{{ key }}` placeholders with HTML-escaped context values."""

    def repl(match: re.Match[str]) -> str:
        return html.escape(context.get(match.group(1), ""))

    return _PLACEHOLDER.sub(repl, template_html)


def render_contract_html(
    template_html: str,
    variables: dict[str, object],
    initiator: dict[str, object],
    counterparty: dict[str, object],
    *,
    contract_public_id: str,
    generated_at: str,
) -> str:
    """Deterministically render a contract to HTML (no hidden timestamps/randomness)."""
    context: dict[str, str] = {
        "contract_public_id": contract_public_id,
        "generated_at": generated_at,
    }
    for key, value in initiator.items():
        context[f"initiator_{key}"] = "" if value is None else str(value)
    for key, value in counterparty.items():
        context[f"counterparty_{key}"] = "" if value is None else str(value)
    for key, value in variables.items():
        context[key] = "" if value is None else str(value)
    return _fill(template_html, context)


def html_to_pdf(html_str: str) -> bytes:
    """Render HTML → PDF bytes via WeasyPrint (lazy import — native libs required)."""
    from weasyprint import HTML  # noqa: PLC0415 — heavy native deps, import on demand

    return bytes(HTML(string=html_str).write_pdf())


def render_contract_pdf(
    template_html: str,
    variables: dict[str, object],
    initiator: dict[str, object],
    counterparty: dict[str, object],
    *,
    contract_public_id: str,
    generated_at: str,
) -> bytes:
    """Convenience: render the HTML then convert to PDF bytes."""
    rendered = render_contract_html(
        template_html, variables, initiator, counterparty,
        contract_public_id=contract_public_id, generated_at=generated_at,
    )
    return html_to_pdf(rendered)
