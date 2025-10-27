from typing import List, Optional
import os
import logging

from fastapi import APIRouter, HTTPException
import json
from chroma_manager import chroma_manager, get_chroma_db
from pcr_services import get_pcr_records_from_chroma
from pydantic import BaseModel

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Chat"])

# Server-controlled system prompt (kept here so frontend cannot modify it)
SYSTEM_PROMPT = (
    "你是 ESG AI 顧問，一位專業的永續與 ESG 顧問。\n"
    "請以禮貌、專業且簡明的中文回覆使用者，提供實用、可操作的建議。\n"
    "當需要引用內部資料時，請明確說明您引用的文件標題與編號，但不要提及內部工具、API 或函式名稱（例如不要寫「pcr_chroma_search」）。\n"
    "如果使用者詢問需要法律、會計或醫療等專業領域的最終決策，請建議聯絡相關執業專業人士。\n"
)

# Tool-calling protocol note (kept server-side):
# If the model decides it should use the Chroma RAG tool, it should output a single-line JSON
# object exactly in this form (and nothing else):
# {"tool": "pcr_chroma_search", "input": "<search text>"}
# The router will detect this, run the tool, and then call Gemini again with the tool results
# so the assistant can produce a final, grounded response.



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


def sanitize_reply(text: str) -> str:
    """Remove internal tool/function names or boilerplate that mentions the tool implementation.
    Keeps document citations but strips phrases like '工具 pcr_chroma_search 已執行' or explicit function names."""
    if not text:
        return text
    # remove lines that mention pcr_chroma_search or '工具' followed by function-like tokens
    import re

    lines = text.splitlines()
    cleaned_lines = []
    for ln in lines:
        if re.search(r"pcr_chroma_search", ln, re.IGNORECASE):
            continue
        if re.search(r"工具[^\n]*已執行", ln):
            continue
        cleaned_lines.append(ln)
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned


@router.post("/api/chat")
async def api_chat(body: ChatRequest):
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

        # Use google-genai function-calling if available
        if genai is not None and types is not None:
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                client = genai.Client(api_key=api_key)
            else:
                client = genai.Client()

            # function declaration for the model
            func_decl = {
                "name": "pcr_chroma_search",
                "description": "Search PCR records using Chroma vector index. Returns list of records with title, developer, regno and snippet.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search": {"type": "string", "description": "search query"},
                        "limit": {"type": "integer", "description": "max documents to return"},
                    },
                    "required": ["search"],
                },
            }

            tool = types.Tool(function_declarations=[func_decl])
            config = types.GenerateContentConfig(tools=[tool])

            # Ask the model allowing it to call the declared function
            response = client.models.generate_content(model=model, contents=prompt_text, config=config)

            # Inspect candidates.content.parts thoroughly and log for debugging
            func_call = None
            try:
                cands = getattr(response, "candidates", []) or []
                logger.debug(f"genai returned {len(cands)} candidates")
                # Iterate candidates and their parts to find function_call or text parts
                for ci, cand in enumerate(cands):
                    parts = getattr(cand.content, "parts", []) or []
                    logger.debug(f"candidate[{ci}] has {len(parts)} parts")
                    for pi, part in enumerate(parts):
                        # Log available attributes for debugging
                        text = getattr(part, "text", None)
                        fc = getattr(part, "function_call", None)
                        ts = getattr(part, "thought_signature", None)
                        logger.info(f"candidate[{ci}].part[{pi}] text={bool(text)} func_call={bool(fc)} thought_signature={bool(ts)}")
                        if text:
                            logger.debug(f"part text (truncated): {str(text)[:400]}")
                        if ts:
                            logger.debug(f"thought_signature: {ts}")
                        if fc:
                            # found a function call; capture it and break
                            func_call = fc
                            logger.info(f"Found function_call in candidate[{ci}].part[{pi}]: name={getattr(fc,'name',None)}")
                            break
                    if func_call:
                        break
            except Exception as e:
                logger.exception("Error while inspecting model response parts: %s", e)
                func_call = None

            # If the model invoked pcr_chroma_search via function_call, execute it
            if func_call and getattr(func_call, "name", None) == "pcr_chroma_search":
                raw_args = getattr(func_call, "args", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                search_text = str(args.get("search", "")).strip()
                limit = int(args.get("limit", 3)) if args.get("limit") else 3

                # ensure chroma
                if getattr(chroma_manager, "_db", None) is None:
                    try:
                        chroma_manager.initialize_db()
                    except Exception as init_err:
                        logger.error("初始化 ChromaDB 失敗: %s", init_err)
                        SESSIONS[sid].append({"role": "assistant", "content": "(執行工具時發生錯誤，無法存取檔案索引)"})
                        return {"reply": "無法存取檔案索引。請稍後再試。", "session_id": sid}

                db = get_chroma_db()
                try:
                    records = await get_pcr_records_from_chroma(db, skip=0, limit=limit, search=search_text)
                except Exception as e:
                    logger.exception("Chroma 檢索失敗: %s", e)
                    SESSIONS[sid].append({"role": "assistant", "content": "(執行工具時發生錯誤)"})
                    return {"reply": "檢索時發生錯誤。", "session_id": sid}

                func_result = []
                for r in records:
                    func_result.append({
                        "document_name": getattr(r, "document_name", ""),
                        "developer": getattr(r, "developer", ""),
                        "pcr_reg_no": getattr(r, "pcr_reg_no", ""),
                        "snippet": (getattr(r, "page_content", "") or "")[:800],
                    })

                tool_output_text = json.dumps({"results": func_result}, ensure_ascii=False)
                # Provide the model with the tool results but avoid naming the internal tool.
                followup_prompt = (
                    SYSTEM_PROMPT
                    + "\n\n以下為檢索到的相關 PCR 文件（JSON 格式）：\n"
                    + tool_output_text
                    + "\n\n請根據上述文件結果，以中文向使用者回覆，並在回答中引用文件名稱與 PCR 登錄編號（不要提及內部工具或函式名稱）。\n\nAssistant:"
                )

                final_resp = client.models.generate_content(model=model, contents=followup_prompt)
                final_text = getattr(final_resp, "text", None) or str(final_resp)
                final_text = sanitize_reply(final_text)
                SESSIONS[sid].append({"role": "assistant", "content": final_text})
                return {"reply": final_text, "session_id": sid}

            # no function call -> treat as normal reply
            reply_text = getattr(response, "text", None) or str(response)
            reply_text = sanitize_reply(reply_text)
            SESSIONS[sid].append({"role": "assistant", "content": reply_text})
            return {"reply": reply_text, "session_id": sid}

            # fallback when genai or types not available
            reply_text = call_gemini_prompt(prompt_text)
            reply_text = sanitize_reply(reply_text)
            SESSIONS[sid].append({"role": "assistant", "content": reply_text})
            print(SESSIONS[sid])
            return {"reply": reply_text, "session_id": sid}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in /api/chat")
        raise HTTPException(status_code=500, detail="Internal server error")
