"""Portal notifications: the `PortalNotification` model and the client read surface.

**`notification_service` deliberately does NOT live here.** It is shared kernel by
00-CONTEXT's explicit list — nearly every domain dispatches through it — so this domain
owns the row and the portal's view of it while the dispatcher stays in `app/services/`.
That split is intentional; do not "reunite" them.
"""
