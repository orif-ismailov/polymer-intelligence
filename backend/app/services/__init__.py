# Shared kernel. This list is CLOSED — see .planning/backend-domain-reorg/P11-REMAINDER.md.
#
# Business logic lives in app/domains/<name>/. What remains here is genuinely
# cross-cutting: imported by most domains, owned by none. After the domain reorg,
# "still in app/services/" means KERNEL, not "not yet moved" — removing that ambiguity
# is the whole point of closing the list.
#
#   audit_service              write_audit, called from nearly every domain
#   auth_service               staff login/JWT — the authorization substrate
#   event_service              transactional outbox
#   event_types                its event-name constants
#   notification_service       the dispatcher. The notifications DOMAIN owns the row and
#                              the portal read surface — that split is deliberate
#   storage_service            S3/MinIO presign + upload
#   settings_service           runtime app_settings knobs
#   rate_limit                 Redis counters
#   dashboard_summary_service  presentation for the internal dashboard; kept together
#                              with app/schemas/dashboard.py + app/api/dashboard.py (P9)
#
# Adding a file here needs a reason of the same kind. If it has an owner, it belongs in
# that owner's domain folder.
