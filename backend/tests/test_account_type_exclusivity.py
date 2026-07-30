"""Account-type exclusivity for company business roles (DB-free)."""

from __future__ import annotations

import pytest

from app.models.enums import CompanyBusinessRole
from app.services.company_service import InvalidBusinessRoles, assert_single_account_type


@pytest.mark.parametrize(
    "roles",
    [
        [],
        [CompanyBusinessRole.importer],
        [CompanyBusinessRole.manufacturer],
        [CompanyBusinessRole.logistics_provider],
        [CompanyBusinessRole.laboratory],
        [CompanyBusinessRole.trader],
        [CompanyBusinessRole.distributor],
        [CompanyBusinessRole.distributor, CompanyBusinessRole.trader],
        [CompanyBusinessRole.trader, CompanyBusinessRole.distributor],
    ],
)
def test_single_account_type_allowed(roles: list[CompanyBusinessRole]) -> None:
    assert_single_account_type(roles)  # does not raise


@pytest.mark.parametrize(
    "roles",
    [
        [CompanyBusinessRole.manufacturer, CompanyBusinessRole.trader],
        [CompanyBusinessRole.importer, CompanyBusinessRole.trader],
        [CompanyBusinessRole.distributor, CompanyBusinessRole.importer],
        [CompanyBusinessRole.manufacturer, CompanyBusinessRole.importer],
        [CompanyBusinessRole.logistics_provider, CompanyBusinessRole.laboratory],
        [CompanyBusinessRole.manufacturer, CompanyBusinessRole.logistics_provider],
        # insurance_provider is in the enum but not an account-type card
        [CompanyBusinessRole.insurance_provider],
    ],
)
def test_cross_account_type_rejected(roles: list[CompanyBusinessRole]) -> None:
    with pytest.raises(InvalidBusinessRoles):
        assert_single_account_type(roles)
