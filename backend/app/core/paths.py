"""Filesystem anchors for things that live beside `app/`, not inside it.

`parsing/` is a top-level package next to `app/`, so modules under `app/` reach it by
walking up from their own location. Doing that with `Path(__file__).parent.parent.parent`
hard-codes how deep the calling module happens to sit — which silently breaks the moment
that module moves. The domain reorg moves modules by design, and it broke exactly this
way twice: `substance_ai` (P6) and `report_service` (P8) each went one directory deeper
and started resolving to a `backend/app/parsing/prompts` that does not exist.

Anchoring here fixes the depth once. `app/core/` is shared kernel — 00-CONTEXT keeps it
out of `app/domains/` permanently — so `parents[2]` is stable by rule, not by luck.

Failure mode worth knowing: `report_service._load_prompt` returns "" for a missing file
and falls back, so a wrong path degrades silently; `substance_ai._load_prompt` raises.
Neither is a good way to discover a path bug, hence the constant.
"""

from pathlib import Path

#: `backend/` — the repo's backend root, two levels above `app/core/`.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: The repo root — home of the ONE `.env` an operator edits.
#:
#: `Settings` used to load `env_file=".env"`, which pydantic resolves against the
#: CURRENT WORKING DIRECTORY, and this repo had both `./.env` and
#: `./backend/.env`. Which one configured the app depended entirely on where you
#: launched it: `make dev` runs uvicorn from `backend/` and got that one, while
#: compose passes the root file — and the two disagreed on ten keys, including
#: `JWT_SECRET` and the S3 credentials. `backend/.env` is now merged into the
#: root file and gone; anchoring here rather than to a relative path is what
#: stops a newly-created `backend/.env` from silently re-forming the split.
REPO_ROOT = BACKEND_ROOT.parent

#: Versioned, immutable LLM prompts (`parsing/prompts/<family>_v<N>.md`).
PROMPTS_DIR = BACKEND_ROOT / "parsing" / "prompts"
