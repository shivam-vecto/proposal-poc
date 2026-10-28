# session_manager.py
import uuid
from datetime import datetime
from typing import Optional

SESSIONS: dict[str, dict] = {}

STAGE_AWAITING_UPLOAD = "AWAITING_UPLOAD"
STAGE_COLLECTING      = "COLLECTING"
STAGE_CONFIRMING      = "CONFIRMING"
STAGE_DONE            = "DONE"


def _blank(sid: str) -> dict:
    return {
        "id": sid,
        "stage": STAGE_AWAITING_UPLOAD,
        "filename": None,
        "document_type": None,
        "extracted_data": {},
        "missing_fields": [],     # primary fields still missing
        "followup_queue": [],     # queued follow-up questions
        "current_field": None,
        "history": [],
        "attachments": [],   # list of {"filename": str, "path": str}
        "created_at": datetime.now().isoformat(),
    }


def create_session() -> dict:
    sid = str(uuid.uuid4())[:8]
    SESSIONS[sid] = _blank(sid)
    return SESSIONS[sid]


def get_session(sid: str) -> Optional[dict]:
    return SESSIONS.get(sid)


def log(session: dict, role: str, content: str):
    session["history"].append({
        "role": role, "content": content,
        "ts": datetime.now().isoformat(),
    })