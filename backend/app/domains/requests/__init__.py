"""Buyer-requests domain: the RFQ a buyer submits, and everything done to it.

`models.py` also declares `Client` — the Telegram-side requester identity. That is not
a squatter: a request is always made by a client, and `client_service` plus
`app/api/webapp/me.py` move into this folder in P11, which is also when
`webapp_schemas.ClientProfileOut`/`ClientProfilePatch` stop looking out of place here.

`rfq_push.py` and `supplier_matching.py` arrived from P5: neither touches a deal or a
payment. They are outbound actions on a buyer request — rank candidate suppliers, then
record that each was told exactly once.
"""
