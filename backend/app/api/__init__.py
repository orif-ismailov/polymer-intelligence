# Shared-kernel routers + DI. This list is CLOSED — see
# .planning/backend-domain-reorg/P11-REMAINDER.md.
#
# Every domain's routers live in app/domains/<name>/api_*.py and are mounted from
# app/main.py at unchanged paths. What remains here has no single owner:
#
#   deps.py               RBAC guards (require_admin / require_analyst_or_admin /
#                         get_current_account) — depended on by every router
#   portal/deps.py        the portal's shared guards (P2): company_or_404,
#                         require_business_role, require_company_admin, rate_limited
#   auth.py               staff login/refresh
#   admin_users.py        staff administration — authorization, not a "staff domain"
#   admin_settings.py     the runtime app_settings surface
#   dashboard.py          internal-dashboard KPIs (kept with dashboard_summary_service
#                         and app/schemas/dashboard.py — one presentation layer, P9)
#   health.py             liveness/readiness
#   telegram_webhook.py   the bot's inbound webhook
#
# app/api/portal/ and app/api/webapp/ now hold only __init__.py (and portal/deps.py).
# A new router under either almost certainly belongs in a domain folder instead.
