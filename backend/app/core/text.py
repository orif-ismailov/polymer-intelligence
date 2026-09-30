"""Free-text input rules shared by the schemas that accept them.

`reject_markup` exists because of audit IMEX-06. Offer text is PLAIN text: React
escapes it everywhere it is shown, and the Telegram notifications escape it now too
(`app/tasks/notify.py`). Refusing a tag at the door is the second layer — a value
that looks like HTML is never a polymer grade, and storing one leaves it waiting for
the first renderer that forgets to escape.

It refuses rather than strips. Silently rewriting what a seller typed would publish
text they never wrote, and a 422 names the field so the form can say why.
"""

from __future__ import annotations

import re

#: A tag as an HTML parser sees one, not a comparison: `<` IMMEDIATELY followed by a
#: letter (optionally after `/`, `!` or `?`) or by `!--`, then a closing `>`. So
#: `<script>`, `</b>`, `<!-- -->` and `<img src=x onerror=…>` are refused, while
#: `MFI <2`, `a < b > c` and `<-` stay ordinary text — `< b` is not a tag to a browser.
_TAG = re.compile(r"<(?:[/!?]?[A-Za-z]|!--)[^<>]*>")


def reject_markup(value: str | None) -> str | None:
    """Return `value` unchanged, or raise `ValueError` if it contains an HTML tag."""
    if value is not None and _TAG.search(value):
        raise ValueError("HTML markup is not allowed")
    return value
