"""Product names on the storefront: which column serves which UI language.

The reference data carries ru/uz/en names. The portal also speaks tr/fa/zh, and
for those readers English — not Russian — is the name they can read, so the
fallback for a language with no column of its own is English, then Russian.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("ru", "Полипропилен"),
        ("uz", "Polipropilen"),
        ("en", "Polypropylene"),
        ("tr", "Polypropylene"),
        ("fa", "Polypropylene"),
        ("zh", "Polypropylene"),
    ],
)
def test_each_language_gets_a_name_it_can_read(lang: str, expected: str) -> None:
    from app.domains.storefront.service import _label  # noqa: PLC0415

    assert _label("Полипропилен", "Polipropilen", "Polypropylene", lang) == expected


def test_missing_english_falls_back_to_russian() -> None:
    from app.domains.storefront.service import _label  # noqa: PLC0415

    assert _label("Полипропилен", None, None, "zh") == "Полипропилен"
    assert _label("Полипропилен", None, None, "uz") == "Полипропилен"
