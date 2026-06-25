"""
Celery task: AI-analyse a buyer purchase request (Phase 5).

Enqueued on request creation (and re-runnable via POST /requests/{id}/analyze). Loads
the request, runs request_analysis_service.analyze_request (LLM → requests.ai), and
commits. Wrapped so it never raises — a failed analysis must not affect the worker or
the request itself; the dashboard panel simply keeps its placeholders.

Queue: parse (shares the LLM/budget lane with the extractor).
"""

from __future__ import annotations

import logging
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="analyze_request_ai", queue="parse")  # type: ignore[untyped-decorator]
def analyze_request_ai(request_id: int) -> dict[str, Any]:
    """Run LLM analysis for one request and persist it to requests.ai.

    Returns a dict: status ("ok" | "skipped" | "not_found" | "error"), request_id,
    and error (str | None). Never raises (T-03-13 analog — worker stays alive).
    """
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from app.core.db import engine  # noqa: PLC0415
    from app.models.requests import Request  # noqa: PLC0415
    from app.services import request_analysis_service  # noqa: PLC0415

    try:
        with Session(engine) as session:
            request = session.get(Request, request_id)
            if request is None:
                logger.warning(
                    "analyze_request_ai.not_found", extra={"request_id": request_id}
                )
                return {"status": "not_found", "request_id": request_id, "error": None}

            ai = request_analysis_service.analyze_request(session, request)
            session.commit()
            return {
                "status": "ok" if ai else "skipped",
                "request_id": request_id,
                "error": None,
            }
    except Exception as exc:
        logger.error(
            "analyze_request_ai.error",
            extra={"request_id": request_id, "error": str(exc)},
        )
        return {"status": "error", "request_id": request_id, "error": str(exc)}
