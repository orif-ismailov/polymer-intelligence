"""Portal identity: the `UserAccount` a person logs into, and its credentials.

`models.py` has ~48 importers, nearly all via `deps.get_current_account`. High fan-in
does NOT make it shared kernel — `models/companies.py` has more and is unambiguously a
domain. The test this track applies is *does it have an owner*, and accounts does:
`service.py` authenticates them and `admin_service.py` issues their credentials.
Contrast `app/models/staff.py`, which has no owner (StaffUser is authorization,
AuditLog is written from everywhere) and is therefore declared kernel.
"""
