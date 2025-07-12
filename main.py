# main.py (主應用程式檔案)
from fastapi import FastAPI, Request, Header, HTTPException
from langchain_community.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv
import os
import logging

# 從 line_helpers.py 引入相關函數和變數
# 在您的本地環境中，這會是一個實際的檔案引入
from line_helpers import reply_line, LINE_CHANNEL_ACCESS_TOKEN 

# 配置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 加載環境變量
load_dotenv()

# 在 main.py 中再次檢查 LINE_CHANNEL_ACCESS_TOKEN，以確保在應用程式啟動前就發現問題
# 雖然 line_helpers.py 內部也會檢查，但這裡提供一個更早的提示
if not LINE_CHANNEL_ACCESS_TOKEN:
    logger.error("環境變量 'LINE_CHANNEL_ACCESS_TOKEN' 未設置。請檢查 .env 文件或 line_helpers.py 的初始化。")
    # 在實際部署中，您可能需要在此處退出或拋出異常
    # raise ValueError("LINE_CHANNEL_ACCESS_TOKEN is not set.")


app = FastAPI()
llm = ChatOpenAI(temperature=0, model="gpt-4")
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# 用戶狀態
user_states = {} # 儲存每個用戶的對話流程階段和相關數據

# 流程簡易描述 (給 AI)
flow_steps = """
- START：詢問用戶要查詢什麼。
- WAITING_PRODUCT：請用戶提供產品 CCC code 或名稱。
- CHECKING_PCR：系統正在判斷產品是否有 PCR。
- PCR_FOUND：提供 PCR 說明並詢問是否還有疑問。
- NO_PCR_FOUND：告知用戶沒有找到 PCR，並詢問是否需要其他協助。
- WAITING_DETAILED_INFO：請用戶提供中英文名稱、規格尺寸、標準。
- FINAL_RESPONSE：彙整分析與報價。
- END：結束對話。
"""

# Prompt
prompt_template = """
你是一位專業的 AI 永續顧問，根據以下對話流程幫助用戶：

流程：
{flow}

目前流程階段：{current_state}

用戶輸入：
{input}

{pcr_check_status} # 新增變數，用於傳遞 PCR 檢查結果

請根據上下文自然地回覆，並在需要時詢問以推進流程。
請在你的回覆中，明確指出下一個預期的流程階段，例如：
如果需要產品資訊，請在回覆中包含 "[NEXT_STATE: WAITING_PRODUCT]"。
如果需要詳細資訊，請在回覆中包含 "[NEXT_STATE: WAITING_DETAILED_INFO]"。
如果流程結束，請在回覆中包含 "[NEXT_STATE: END]"。
如果確認有 PCR，請在回覆中包含 "[NEXT_STATE: PCR_FOUND]"。
如果確認沒有 PCR，請在回覆中包含 "[NEXT_STATE: NO_PCR_FOUND]"。
"""

prompt = PromptTemplate(
    input_variables=["flow", "current_state", "input", "pcr_check_status"], # 更新 input_variables
    template=prompt_template
)

# 新增函數：模擬 PCR 資料庫查詢
def simulate_pcr_check(product_query: str) -> bool:
    """
    模擬查詢環境部網站的 PCR 資料庫。
    在實際應用中，這裡會是發送 HTTP 請求到網站並解析內容的邏輯，
    或者查詢本地資料庫的邏輯。
    為了演示，我們簡單地根據輸入內容判斷。
    """
    logger.info(f"模擬 PCR 檢查，查詢內容: '{product_query}'")
    # 簡單判斷：如果查詢中包含 '碳足跡' 或 'PCR' 或 '12345', 則模擬找到 PCR
    # 您可以根據實際的 CCC code 或產品名稱來擴展這個模擬邏輯
    if "碳足跡" in product_query.lower() or "pcr" in product_query.lower() or "12345" in product_query:
        logger.info("模擬結果：找到 PCR。")
        return True
    logger.info("模擬結果：未找到 PCR。")
    return False

# 新增函數：根據 LLM 回覆判斷下一個狀態
def determine_next_state_from_llm_reply(current_state: str, llm_reply: str) -> str:
    """
    根據 LLM 的回覆內容，嘗試判斷下一個對話狀態。
    這裡使用簡單的關鍵字匹配。在實際應用中，可以考慮使用 LLM 的結構化輸出 (例如 JSON)
    或更複雜的意圖識別模型。
    """
    # 檢查 LLM 回覆中是否包含明確的狀態指示
    if "[NEXT_STATE: WAITING_PRODUCT]" in llm_reply:
        return "WAITING_PRODUCT"
    elif "[NEXT_STATE: CHECKING_PCR]" in llm_reply:
        return "CHECKING_PCR"
    elif "[NEXT_STATE: PCR_FOUND]" in llm_reply:
        return "PCR_FOUND"
    elif "[NEXT_STATE: NO_PCR_FOUND]" in llm_reply: # 新增此狀態判斷
        return "NO_PCR_FOUND"
    elif "[NEXT_STATE: WAITING_DETAILED_INFO]" in llm_reply:
        return "WAITING_DETAILED_INFO"
    elif "[NEXT_STATE: FINAL_RESPONSE]" in llm_reply:
        return "FINAL_RESPONSE"
    elif "[NEXT_STATE: END]" in llm_reply:
        return "END"
    
    # 如果 LLM 沒有明確指示，則根據當前狀態進行預設的線性推進
    logger.warning(f"LLM 回覆中未找到明確的狀態指示。當前狀態: {current_state}，回覆: {llm_reply[:50]}...")
    # 這裡的後備邏輯需要更仔細考慮，以避免無限循環或不正確的狀態跳轉
    # 為了演示，我們仍然保留一個簡單的線性後備
    if current_state == "START":
        return "WAITING_PRODUCT"
    elif current_state == "WAITING_PRODUCT":
        # 如果用戶提供了產品資訊，但 LLM 沒有明確指示，我們假設進入 CHECKING_PCR 階段
        return "CHECKING_PCR"
    elif current_state == "CHECKING_PCR":
        # 如果 LLM 在 CHECKING_PCR 階段沒有明確指示，這是一個問題，可能需要更強健的錯誤處理
        # 這裡暫時保持當前狀態，等待 LLM 給出明確指示
        return "CHECKING_PCR" # 保持在 CHECKING_PCR，直到 LLM 給出明確結果
    elif current_state == "PCR_FOUND":
        return "WAITING_DETAILED_INFO"
    elif current_state == "NO_PCR_FOUND":
        return "WAITING_PRODUCT" # 如果沒有找到 PCR，可能希望用戶提供其他產品
    elif current_state == "WAITING_DETAILED_INFO":
        return "FINAL_RESPONSE"
    elif current_state == "FINAL_RESPONSE":
        return "END"
    
    return current_state # 如果沒有匹配到，保持當前狀態

@app.post("/webhook")
async def line_webhook(request: Request, x_line_signature: str = Header(None)):
    """
    處理來自 LINE 平台的 Webhook 請求。
    """
    logger.info("收到 LINE Webhook 請求。")
    try:
        body = await request.json()
        logger.info(f"Webhook 請求體: {body}")
    except Exception as e:
        logger.error(f"解析 Webhook 請求體失敗: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    events = body.get("events", [])
    if not events:
        logger.warning("Webhook 請求體中沒有事件。")
        return "OK"

    for event in events:
        logger.info(f"處理事件: {event.get('type')}")
        if event.get("type") == "message" and event["message"].get("type") == "text":
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]
            user_id = event["source"]["userId"]
            
            logger.info(f"收到用戶 '{user_id}' 的訊息: '{user_message}'")

            # 預設 START 狀態，如果用戶沒有狀態則初始化
            current_state = user_states.get(user_id, {}).get("current_state", "START")
            
            # 儲存用戶最近的產品查詢，以便在 CHECKING_PCR 階段使用
            if current_state == "WAITING_PRODUCT":
                user_states.setdefault(user_id, {})["product_query"] = user_message
                # 立即將狀態推進到 CHECKING_PCR，以便在下一輪 LLM 呼叫時執行檢查
                user_states[user_id]["current_state"] = "CHECKING_PCR"
                current_state = "CHECKING_PCR" # 更新當前迴圈的狀態
            
            logger.info(f"用戶 '{user_id}' 當前流程階段: {current_state}")

            pcr_check_status_for_prompt = "" # 預設為空，除非進行了 PCR 檢查

            # 在 CHECKING_PCR 階段執行模擬的 PCR 檢查
            if current_state == "CHECKING_PCR":
                product_query = user_states.get(user_id, {}).get("product_query", "")
                if product_query:
                    pcr_found = simulate_pcr_check(product_query)
                    if pcr_found:
                        pcr_check_status_for_prompt = "系統已檢查：該產品可能存在 PCR 資料。"
                    else:
                        pcr_check_status_for_prompt = "系統已檢查：該產品似乎沒有找到 PCR 資料。"
                else:
                    logger.warning(f"在 CHECKING_PCR 階段未找到產品查詢資訊 for user: {user_id}")
                    pcr_check_status_for_prompt = "系統在檢查 PCR 時未收到有效的產品資訊，請重新提供。"
            
            # LangChain 輸入
            ai_input = prompt.format(
                flow=flow_steps,
                current_state=current_state,
                input=user_message,
                pcr_check_status=pcr_check_status_for_prompt
            )
            logger.info("呼叫 LangChain LLM 進行預測...")
            try:
                bot_reply = llm.predict(ai_input)
                logger.info(f"LangChain LLM 回覆: {bot_reply}")
            except Exception as e:
                logger.error(f"LangChain LLM 預測失敗: {e}")
                bot_reply = "抱歉，AI 服務目前無法回應，請稍後再試。"
            
            # 根據 LLM 的回覆內容來判斷下一個流程階段
            next_state = determine_next_state_from_llm_reply(current_state, bot_reply)
            user_states.setdefault(user_id, {})["current_state"] = next_state
            
            logger.info(f"用戶 '{user_id}' 新的流程階段: {user_states[user_id]['current_state']}")

            # 回覆 LINE 訊息 (將 LLM 回覆中的狀態標記移除，只回覆實際內容)
            clean_bot_reply = bot_reply.split("[NEXT_STATE:")[0].strip()
            await reply_line(reply_token, [{"type": "text", "text": clean_bot_reply}])
        else:
            logger.info(f"收到非文本訊息或非訊息事件，類型: {event.get('type')}")

    return "OK"
