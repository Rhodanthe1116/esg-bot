from typing import List, Optional
import os
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from google import genai
except Exception:
    genai = None

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Chat"])

# Server-controlled system prompt (kept here so frontend cannot modify it)
SYSTEM_PROMPT = (
    "你是 ESG AI 顧問，一位專業的永續與 ESG 顧問。\n"
    "請以禮貌、專業且簡明的中文回覆使用者，提供實用、可操作的建議。\n"
    "當需要引用內部資料或工具時，請明確說明你使用了哪些資訊來源。\n"
    "如果使用者詢問需要法律、會計或醫療等專業領域的最終決策，請建議聯絡相關執業專業人士。\n"
)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    session_id: Optional[str] = None


# Simple in-memory session store: { session_id: [ {role, content}, ... ] }
SESSIONS = {}


def call_gemini_prompt(prompt_text: str) -> str:
    """
    Call Gemini using the official google-genai client only.
    This function requires the `google-genai` package to be installed.
    """
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    api_key = os.getenv("GEMINI_API_KEY")

    if genai is None:
        raise RuntimeError(
            "google-genai SDK is not installed. Please install it: `pip install google-genai` and ensure credentials are configured."
        )

    try:
        # Optionally pass api_key to client; the SDK may also use ADC
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            client = genai.Client()

        response = client.models.generate_content(model=model, contents=prompt_text)
        # Try common access patterns
        text = getattr(response, "text", None)
        if text:
            return text

        # Try candidates array or structured results if present
        if hasattr(response, "candidates"):
            cands = getattr(response, "candidates")
            if isinstance(cands, list) and cands:
                first = cands[0]
                if isinstance(first, dict) and "output" in first:
                    return first["output"]
                t = getattr(first, "text", None)
                if t:
                    return t

        # Fallback: string representation
        return str(response)
    except Exception as e:
        logger.exception("google.genai client call failed: %s", e)
        raise RuntimeError(f"google-genai client call failed: {e}")


@router.post("/api/chat")
def api_chat(body: ChatRequest):
    """
    Simple chat endpoint used by the front-end.
    Accepts JSON: { messages: [{role, content}, ...] }
    Returns: { reply: str }
    """
    try:
        # determine session id
        sid = body.session_id
        if not sid:
            # create a simple session id (timestamp-based)
            import time

            sid = str(int(time.time() * 1000))

        # ensure session exists
        if sid not in SESSIONS:
            SESSIONS[sid] = []

        # append incoming messages to session store
        for m in body.messages:
            SESSIONS[sid].append({"role": m.role or "user", "content": m.content})

        # build prompt from session history (last 40 messages to be safe)
        parts = []
        for m in SESSIONS[sid][-40:]:
            role = m.get("role", "user")
            parts.append(f"[{role}] {m.get('content', '')}")

        # Prepend the server-side system instructions to ensure consistent assistant behavior
        prompt_text = SYSTEM_PROMPT + "\n\n" + "\n".join(parts) + "\n\nAssistant:"

        reply_text = call_gemini_prompt(prompt_text)

        # persist assistant reply
        SESSIONS[sid].append({"role": "assistant", "content": reply_text})
        print(SESSIONS[sid])
        return {"reply": reply_text, "session_id": sid}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in /api/chat")
        raise HTTPException(status_code=500, detail="Internal server error")
