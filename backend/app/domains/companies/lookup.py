"""Registry prefill for company registration (R6 / P7.a — Stage 1).

The wizard asks a person to type what the state already knows. Didox's
`/v1/utils/info/{tin}` answers with the tax registry's record, so once the STIR
is known — from the E-IMZO certificate at step 1, or typed — the rest of the form
can arrive filled in.

Three rules this module exists to hold:

  * **The channel is an operator decision.** Prefill runs only when
    `gov_registry_mode` is `didox` AND a partner token is configured. Otherwise
    it raises, the form stays manual, and nothing is silently different between
    environments.
  * **Absence is not emptiness.** `CompanyNotFound` propagates so the caller can
    say "not found" instead of blanking a form with nulls.
  * **Company requisites yes, personal identifiers no.** The lookup response
    carries the director's ПИНФЛ and tax id; those never leave this module. Any
    portal account can call this endpoint for any STIR, so what it returns must
    be what a counterparty would read off an invoice — legal name, address, ОКЭД,
    bank requisites, the director's NAME — and nothing that identifies a private
    person beyond it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.integrations import gov_registry
from app.integrations.didox import is_configured
from app.integrations.didox.client import DidoxCompanyInfo
from app.integrations.didox.registry import CompanyNotFound, DidoxGovRegistryClient

if TYPE_CHECKING:  # pragma: no cover
    import redis

logger = logging.getLogger(__name__)

__all__ = ["ChannelDisabled", "CompanyNotFound", "lookup_company"]


class ChannelDisabled(gov_registry.ProviderUnavailable):
    """No registry channel is switched on — which is the shipped default.

    Distinct from an outage on purpose. "The provider is down" is worth a line on
    screen; "this deployment does not use a registry" is not, and telling every
    applicant about a feature they have never seen is noise, not transparency.
    The form is identical either way.
    """


def lookup_company(
    db: Session,
    tax_id: str,
    *,
    redis_client: redis.Redis[str] | None = None,
) -> DidoxCompanyInfo:
    """The registry's record for a STIR.

    Raises `CompanyNotFound` when the registry has no such company, and
    `gov_registry.ProviderUnavailable` when there is no usable channel (mode off,
    no token, outage, or — in production — no service `user-key`).
    """
    mode = gov_registry.current_mode()
    if mode != gov_registry.MODE_DIDOX:
        raise ChannelDisabled(
            f"gov_registry: prefill needs gov_registry_mode=didox (currently {mode!r})"
        )
    if not is_configured():
        raise ChannelDisabled("gov_registry: DIDOX_PARTNER_TOKEN is not set")

    return DidoxGovRegistryClient(redis_client=redis_client).fetch_info(tax_id)
