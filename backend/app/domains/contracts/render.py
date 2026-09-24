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

from app.domains.contracts.terms import derived_values

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")

#: `{{#if key}}`, `{{#if key=value}}`, `{{#if key!=value}}` … `{{/if}}`. This pattern
#: matches an INNERMOST block only — its body holds no further `{{#if` — so blocks
#: nest, resolved from the inside out. `templates.validate_body` refuses an
#: unbalanced one before it is saved.
BLOCK = re.compile(
    r"\{\{#if\s+(\w+)\s*(?:(!?=)\s*([\w-]+))?\s*\}\}"
    r"((?:(?!\{\{#if).)*?)\{\{/if\}\}",
    re.DOTALL,
)
BLOCK_OPEN = re.compile(r"\{\{#if\s+(\w+)[^}]*\}\}")
BLOCK_CLOSE = re.compile(r"\{\{/if\}\}")

#: A section (`<h2 data-n>`) or clause (`<p data-n>`) the renderer numbers.
_NUMBERED = re.compile(r"<(h2|p)(\s[^>]*?)?\s+data-n(\s[^>]*)?>", re.IGNORECASE)

_FALSY = frozenset({"", "false", "0", "no"})


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() not in _FALSY


def _blocks(template_html: str, context: dict[str, str]) -> str:
    """Keep each `{{#if}}` block whose condition holds, drop the rest."""

    def repl(match: re.Match[str]) -> str:
        key, op, expected, body = match.groups()
        value = context.get(key)
        if op == "=":
            keep = (value or "") == expected
        elif op == "!=":
            keep = (value or "") != expected
        else:
            keep = _truthy(value)
        return body if keep else ""

    previous = None
    while previous != template_html:
        previous = template_html
        template_html = BLOCK.sub(repl, template_html)
    return template_html


def _number(template_html: str) -> str:
    """Prefix `N.` to each numbered section and `N.M.` to each clause, in order.

    Done after the blocks are resolved, so a switched-off section or clause leaves
    no hole in the numbering. Didox prints its own section number (`ordno`) and
    `contract_docs.sections_from_html` strips ours from the title; the clause
    numbers inside the text agree with it because the order is the same.
    """
    section = 0
    clause = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal section, clause
        tag = match.group(1)
        attrs = (match.group(2) or "") + (match.group(3) or "")
        if tag.lower() == "h2":
            section += 1
            clause = 0
            label = f"{section}."
        else:
            clause += 1
            label = f"{section}.{clause}."
        return f"<{tag}{attrs}>{label} "

    return _NUMBERED.sub(repl, template_html)


def _fill(template_html: str, context: dict[str, str]) -> str:
    """Resolve the blocks, number the sections, substitute HTML-escaped values."""

    def repl(match: re.Match[str]) -> str:
        return html.escape(context.get(match.group(1), ""))

    return _PLACEHOLDER.sub(repl, _number(_blocks(template_html, context)))


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
    # «Поставщик» / «Покупатель» as the contract names them. The initiator
    # supplies unless the form says it is the buyer.
    supplier, buyer = (
        (counterparty, initiator)
        if variables.get("initiator_side") == "buyer"
        else (initiator, counterparty)
    )
    for key, value in supplier.items():
        context[f"supplier_{key}"] = "" if value is None else str(value)
    for key, value in buyer.items():
        context[f"buyer_{key}"] = "" if value is None else str(value)
    context.update(derived_values(variables))
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
