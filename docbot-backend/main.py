# main.py
import json
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import PyPDF2

from config import UPLOAD_DIR, STATIC_DIR
from gemini_client import gemini_json, gemini_text
from pdf_generator import generate_document_pdf
from session_manager import (
    create_session, get_session, log,
    STAGE_AWAITING_UPLOAD, STAGE_COLLECTING, STAGE_CONFIRMING, STAGE_DONE,
)
import questionnaire as Q


app = FastAPI(title="Document Bot — Questionnaire Framework", version="6.1.0")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def extract_text_from_pdf(content: bytes) -> str:
    try:
        reader = PyPDF2.PdfReader(BytesIO(content))
        text = ""
        for i, page in enumerate(reader.pages, 1):
            t = page.extract_text()
            if t:
                text += f"\n--- Page {i} ---\n{t}"
        return text.strip()
    except Exception as e:
        raise HTTPException(400, f"Error reading PDF: {e}")


def extract_questionnaire_fields(pdf_text: str) -> dict:
    """
    Ask Gemini to fill the fixed questionnaire from the document.
    Uses aliases so it recognises insurance/ID/invoice variants.
    """
    fields_block = []
    for q in Q.QUESTION_SET:
        aliases = ", ".join(q["aliases"]) if q["aliases"] else "(none)"
        fields_block.append(f"- {q['field']}  (aliases: {aliases})")

    prompt = f"""
    You are a document data extractor.
    Read the document below and fill in these fixed fields.

    Fields to extract:
    {chr(10).join(fields_block)}

    Rules:
    - Return ONLY valid JSON with a top-level key "extracted_data".
    - Use the CANONICAL field names listed above (not aliases).
    - If a field is not present in the document, set its value to null.
    - For "gender", normalize to Male / Female / Other.
    - If the document contains "date_of_birth" or "dob" but not "age", 
      compute age from date_of_birth using today's date and return it as "age" 
      (integer years only). Do NOT return date_of_birth in the output if age is computed.
    - For "aadhaar_number", extract only the 12 digits (no spaces/dashes).
    - For "pan_number", uppercase, e.g. ABCDE1234F.
    - For "pre_existing_diseases", answer "Yes" or "No" if stated, else null.
    - For "smoking_alcohol", use one of: "No", "Smoking", "Alcohol", "Both", or null.

    Document text:
    {pdf_text[:15000]}

    Return format:
    {{"extracted_data": {{ "full_name": "...", "date_of_birth": "...", ... }} }}
    """
    result = gemini_json(prompt)
    raw = result.get("extracted_data", {}) or {}
    return Q.normalize_alias_keys(raw)


def bulk_extract_from_text(user_text: str) -> dict:
    """
    When the user starts by typing (instead of uploading), try to pull
    as many questionnaire fields as possible from their message.
    """
    fields_block = ", ".join(Q.primary_fields())
    prompt = f"""
    Extract any of these fields that appear in the user's message.
    Fields: {fields_block}

    Rules:
    - Return ONLY valid JSON: {{"extracted_data": {{...}}}}
    - Use canonical field names (snake_case).
    - Normalize dates to YYYY-MM-DD.
    - For "gender" use Male / Female / Other.
    - For "aadhaar_number" extract only the 12 digits.
    - For "pan_number" uppercase, e.g. ABCDE1234F.
    - For "pre_existing_diseases" use "Yes"/"No".
    - For "smoking_alcohol" use "No"/"Smoking"/"Alcohol"/"Both".
    - Omit fields that are not mentioned.

    User message:
    "{user_text}"
    """
    try:
        result = gemini_json(prompt)
        return Q.normalize_alias_keys(result.get("extracted_data", {}) or {})
    except Exception:
        return {}


def build_followup_queue(data: dict) -> list[dict]:
    """Collect follow-up questions triggered by current data, in order."""
    queue = []
    for field in Q.primary_fields():
        if Q.is_blank(data.get(field)):
            continue
        fups = Q.followups_for(field, data[field])
        if fups:
            queue.extend(fups)
    return queue


def next_question(session: dict) -> Optional[str]:
    """
    Returns the next field to ask (primary or follow-up), or None if done.

    Priority: follow-ups FIRST (so ped_details fires immediately after PED=Yes),
    then the remaining primary fields.
    """
    if session["followup_queue"]:
        return session["followup_queue"][0]["field"]
    if session["missing_fields"]:
        return session["missing_fields"][0]
    return None

def compose_summary(data: dict) -> str:
    lines = []
    for f in Q.primary_fields():
        v = data.get(f, "—")
        lines.append(f"• {f.replace('_', ' ').title()}: {v}")
    for extra in ("ped_details", "smoking_frequency", "alcohol_frequency"):
        if data.get(extra):
            lines.append(f"• {extra.replace('_', ' ').title()}: {data[extra]}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "online", "version": "6.1.0"}


@app.post("/chat/start")
async def chat_start():
    s = create_session()
    greeting = (
        "👋 Welcome! I'm your Proposal Assistant.\n"
        "You can:\n"
        "• 📄 Upload your Aadhaar, PAN, insurance, or other supporting documents, or\n"
        "• ✍️ Start entering your details manually.\n"
        "I'll extract the information from your documents and ask only for the details that are missing.\n"
        "Let's get started!"
    )
    log(s, "bot", greeting)
    return {"session_id": s["id"], "stage": s["stage"], "bot_message": greeting}


@app.post("/chat/start-manual")
async def chat_start_manual(req: dict):
    """User chose to type everything — skip extraction, ask all questions."""
    session_id = req.get("session_id")
    s = get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found.")

    s["filename"] = None
    s["document_type"] = "MANUAL_ENTRY"
    s["extracted_data"] = {}
    s["missing_fields"] = Q.primary_fields()
    s["followup_queue"] = []
    s["stage"] = STAGE_COLLECTING
    s["current_field"] = s["missing_fields"][0]

    first = s["current_field"]
    opts = Q.get_options(first)
    msg = ["No problem — let's fill it in together.", "", f"**{Q.get_question(first)}**"]
    if opts:
        msg.append(f"(Options: {' / '.join(opts)})")
    bot_msg = "\n".join(msg)
    log(s, "bot", bot_msg)

    return {
        "session_id": s["id"],
        "stage": s["stage"],
        "extracted_data": {},
        "missing_fields": s["missing_fields"],
        "current_field": first,
        "bot_message": bot_msg,
    }


@app.post("/chat/upload")
async def chat_upload(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    s = get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found. Call /chat/start first.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    content = await file.read()

    # ── Save to disk and remember for the final PDF ──
    saved_path = UPLOAD_DIR / f"{session_id}_{file.filename}"
    saved_path.write_bytes(content)
    s["attachments"].append({
        "filename": file.filename,
        "path": str(saved_path),
    })
    log(s, "user", f"📎 Uploaded: {file.filename}")

    pdf_text = extract_text_from_pdf(content)
    if not pdf_text:
        raise HTTPException(400, "PDF is empty or unreadable.")

    extracted = extract_questionnaire_fields(pdf_text)

    # Merge with anything already collected (in case user typed some fields first)
    merged = {**s.get("extracted_data", {}), **{k: v for k, v in extracted.items() if not Q.is_blank(v)}}
    s["extracted_data"] = merged

    missing = Q.find_missing_fields(merged)
    followups = build_followup_queue(merged)

    s["filename"] = file.filename
    s["document_type"] = "QUESTIONNAIRE"
    s["missing_fields"] = missing
    s["followup_queue"] = followups

    total = len(Q.primary_fields())
    filled = total - len(missing)

    msg = [
        f"📄 I read **{file.filename}**.",
        f"Extracted **{filled}/{total}** fields.",
        "",
    ]
    if filled > 0:
        msg.append("Here's what I found:")
        msg.append(compose_summary(merged))
        msg.append("")

    nxt = next_question(s)
    if nxt:
        s["stage"] = STAGE_COLLECTING
        s["current_field"] = nxt
        opts = Q.get_options(nxt)
        msg.append("I still need a few details:")
        msg.append(f"**{Q.get_question(nxt)}**")
        if opts:
            msg.append(f"(Options: {' / '.join(opts)})")
    else:
        s["stage"] = STAGE_CONFIRMING
        s["current_field"] = None
        msg.append("**Everything is filled in. Shall I generate the PDF? (yes/no)**")

    bot_msg = "\n".join(msg)
    log(s, "bot", bot_msg)

    return {
        "session_id": s["id"],
        "stage": s["stage"],
        "extracted_data": merged,
        "missing_fields": missing,
        "current_field": s.get("current_field"),
        "bot_message": bot_msg,
    }


@app.post("/chat/message")
async def chat_message(req: ChatMessageRequest):
    s = get_session(req.session_id)
    if not s:
        raise HTTPException(404, "Session not found.")

    user_msg = req.message.strip()
    log(s, "user", user_msg)
    stage = s["stage"]

    # ── AWAITING_UPLOAD: user chose to type instead of uploading ──
    if stage == STAGE_AWAITING_UPLOAD:
        extracted = bulk_extract_from_text(user_msg)
        if not extracted:
            bot = (
                "I couldn't read any details from that. You can either:\n"
                "• Upload a Document using the 📎 button, or\n"
                "• Type your details — starting with your full name."
            )
            log(s, "bot", bot)
            return {
                "session_id": s["id"],
                "stage": stage,
                "bot_message": bot,
                "current_field": None,
            }

        s["document_type"] = "MANUAL_ENTRY"
        s["extracted_data"] = extracted
        s["missing_fields"] = Q.find_missing_fields(extracted)
        s["followup_queue"] = build_followup_queue(extracted)
        s["stage"] = STAGE_COLLECTING

        nxt = next_question(s)
        if nxt:
            s["current_field"] = nxt
            opts = Q.get_options(nxt)
            filled = len(Q.primary_fields()) - len(s["missing_fields"])
            bot = (
                f"👍 Got {filled} detail{'s' if filled != 1 else ''} from that.\n\n"
                f" **{Q.get_question(nxt)}**"
            )
            if opts:
                bot += f"\n(Options: {' / '.join(opts)})"
        else:
            s["current_field"] = None
            s["stage"] = STAGE_CONFIRMING
            bot = (
                "🎉 All details collected!\n\n"
                + compose_summary(s["extracted_data"])
                + "\n\nShall I generate the PDF? (yes/no)"
            )

        log(s, "bot", bot)
        return {
            "session_id": s["id"],
            "stage": s["stage"],
            "extracted_data": s["extracted_data"],
            "missing_fields": s["missing_fields"],
            "current_field": s.get("current_field"),
            "bot_message": bot,
        }

    # ── COLLECTING ─────────────────────────────────────────
    if stage == STAGE_COLLECTING:
        field = s["current_field"]
        opts = Q.get_options(field)

        norm_prompt = f"""
        The user was asked: "**{Q.get_question(field)}**"
        Their answer: "{user_msg}"
        {f"Allowed choices: {opts}" if opts else ""}

        Return ONLY valid JSON: {{"value": "<normalized value>"}}
        - For dates, use YYYY-MM-DD.
        - For gender, map to Male/Female/Other.
        - For aadhaar_number, keep only the 12 digits.
        - For pan_number, uppercase letters + digits.
        - For pre_existing_diseases, map to "Yes" or "No".
        - For smoking_alcohol, map to one of: "No","Smoking","Alcohol","Both","Prefer to provide details".
        - If the answer is unclear or empty, return {{"value": null}}.
        """
        try:
            value = gemini_json(norm_prompt).get("value")
        except Exception:
            value = user_msg

        ok, err = Q.validate(field, value)
        if not ok:
            bot = f"⚠️ {err}\n**{Q.get_question(field)}**"
            log(s, "bot", bot)
            return {
                "session_id": s["id"],
                "stage": stage,
                "bot_message": bot,
                "current_field": field,
            }

        # Save
        s["extracted_data"][field] = value

        if field in s["missing_fields"]:
            s["missing_fields"].remove(field)

        s["followup_queue"] = [f for f in s["followup_queue"] if f["field"] != field]

        new_fups = Q.followups_for(field, value) or []
        for nf in new_fups:
            if not any(f["field"] == nf["field"] for f in s["followup_queue"]):
                s["followup_queue"].append(nf)

        nxt = next_question(s)
        if nxt:
            s["current_field"] = nxt
            opts_next = Q.get_options(nxt)
            bot = f"👍 Got it.\n\n **{Q.get_question(nxt)}**"
            if opts_next:
                bot += f"\n(Options: {' / '.join(opts_next)})"
        else:
            s["stage"] = STAGE_CONFIRMING
            s["current_field"] = None
            bot = (
                "🎉 All required information collected!\n\n"
                + compose_summary(s["extracted_data"])
                + "\n\nShall I generate the PDF now? (yes/no)"
            )
        log(s, "bot", bot)
        return {
            "session_id": s["id"],
            "stage": s["stage"],
            "extracted_data": s["extracted_data"],
            "missing_fields": s["missing_fields"],
            "current_field": s.get("current_field"),
            "bot_message": bot,
        }

    # ── CONFIRMING ─────────────────────────────────────────
    if stage == STAGE_CONFIRMING:
        low = user_msg.lower()
        if any(w in low for w in ["yes", "y", "sure", "ok", "generate", "go ahead"]):
            s["stage"] = STAGE_DONE
            bot = "📄 Your PDF is ready! Click the link below to download."
            log(s, "bot", bot)
            return {
                "session_id": s["id"],
                "stage": s["stage"],
                "bot_message": bot,
                "current_field": None,
                "pdf_ready": True,
                "download_url": f"/chat/download/{s['id']}",
            }

        if any(w in low for w in ["no", "edit", "change", "wait"]):
            bot = (
                "No problem. Which field would you like to update?\n"
                "Just say e.g. 'change pincode to 400001' or 'update mobile to 9876543210'."
            )
            log(s, "bot", bot)
            return {"session_id": s["id"], "stage": stage, "bot_message": bot, "current_field": None}

        edit_prompt = f"""
        Current data: {json.dumps(s['extracted_data'])}
        User says: "{user_msg}"

        If the user is editing a field, return:
        {{"action":"edit","field":"<canonical_field>","value":"<new value>"}}
        Otherwise return: {{"action":"unknown"}}
        Canonical fields: {Q.primary_fields()}
        """
        try:
            act = gemini_json(edit_prompt)
        except Exception:
            act = {"action": "unknown"}

        if act.get("action") == "edit" and act.get("field") in Q.primary_fields():
            f, v = act["field"], act["value"]
            s["extracted_data"][f] = v
            bot = (
                f"✅ Updated **{f.replace('_', ' ')}** → `{v}`.\n"
                "Anything else? Reply 'yes' to generate the PDF."
            )
        else:
            bot = "Please reply 'yes' to generate the PDF, or tell me what to change."
        log(s, "bot", bot)
        return {
            "session_id": s["id"],
            "stage": stage,
            "bot_message": bot,
            "extracted_data": s["extracted_data"],
            "current_field": None,
        }

    # ── DONE ───────────────────────────────────────────────
    if stage == STAGE_DONE:
        bot = "This session is complete. Start a new session to process another document."
        return {"session_id": s["id"], "stage": stage, "bot_message": bot, "current_field": None}

    # ── FALLBACK ───────────────────────────────────────────
    bot = "Please upload a PDF using the upload button 📎, or type your details to begin."
    return {"session_id": s["id"], "stage": stage, "bot_message": bot, "current_field": None}


@app.get("/chat/download/{session_id}")
async def chat_download(session_id: str):
    s = get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found.")
    if s["stage"] != STAGE_DONE:
        raise HTTPException(400, "Session not complete yet.")

    # Collect paths of any uploaded PDFs for this session
    attachment_paths = [a["path"] for a in s.get("attachments", [])]

    pdf_bytes = generate_document_pdf(
        "Insurance Proposal",
        s["extracted_data"],
        attachment_paths=attachment_paths,
    )

    # ── Save to disk for audit / re-download ─────────────
    from config import GENERATED_DIR
    filename = f"proposal_{session_id}.pdf"
    saved_path = GENERATED_DIR / filename
    saved_path.write_bytes(pdf_bytes)
    print(f"[download] saved {saved_path} ({len(pdf_bytes)} bytes)")

    # ── Return the same bytes to the client ──────────────
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.get("/chat/schema")
async def chat_schema():
    """
    Returns the full questionnaire schema so the frontend doesn't
    need to hardcode field labels, icons, or options.
    """
    return Q.build_schema()

@app.get("/chat/session/{session_id}")
async def get_session_state(session_id: str):
    s = get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found.")
    return s


# Serve static UI
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)