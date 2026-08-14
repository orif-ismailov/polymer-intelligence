"""The anonymous public storefront — everything a logged-out visitor sees.

`service.py` reads companies, marketplace, pricing and reference, which looks like a
reason to call it shared infrastructure. It is not: it is a SURFACE. One consumer
(`api.py`), one audience (anonymous visitors), one reason to change — the logged-out
home page. A bounded context whose data happens to be borrowed.

Named `storefront` rather than `public` so the folder does not read as a visibility
modifier on the code inside it.
"""
