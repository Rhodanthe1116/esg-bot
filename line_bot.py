from fastapi import APIRouter, Request, Header, HTTPException
from langchain_community.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
)  # 引入 ChatPromptTemplate
from langchain.agents import (
    AgentExecutor,
    create_openai_tools_agent,
)  # 引入 Agent 相關模組
from dotenv import load_dotenv
import logging
from typing import Optional

# 從 line_helpers.py 引入相關函數和變數
from line_helpers import reply_line, LINE_CHANNEL_ACCESS_TOKEN

# 從 tools.py 匯入定義的工具
from tools import pcr_database_search  # 匯入 pcr_database_search 工具

# 配置日誌
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 加載環境變量
load_dotenv()

# 在 line_bot.py 中檢查 LINE_CHANNEL_ACCESS_TOKEN
if not LINE_CHANNEL_ACCESS_TOKEN:
    logger.error(
        "環境變量 'LINE_CHANNEL_ACCESS_TOKEN' 未設置。請檢查 .env 文件或 line_helpers.py 的初始化。"
    )
    # 在實際部署中，您可能需要在此處退出或拋出異常
    # raise ValueError("LINE_CHANNEL_ACCESS_TOKEN is not set.")

# 創建 APIRouter 實例，用於 LINE Bot 相關的路由
router = APIRouter(
    prefix="",  # LINE Webhook 通常在根路徑或特定路徑，這裡不設定前綴，直接定義 /webhook
    tags=["LINE Bot"],  # 在 Swagger UI 中分組
)

llm = ChatOpenAI(temperature=0, model="gpt-4")

# 儲存每個用戶的對話記憶和 Agent 執行器
user_sessions = (
    {}
)  # 儲存 {user_id: {"memory": ConversationBufferMemory, "agent_executor": AgentExecutor}}

# 下載連結的基礎 URL，與前端介面保持一致
DOWNLOAD_BASE_URL = "https://cfp-calculate.tw/cfpc/Carbon/WebPage/"

# 定義 Agent 可以使用的工具列表
tools = [pcr_database_search]

# 定義 Agent 的 Prompt
# 這個 Prompt 將引導 LLM 如何思考和使用工具
agent_prompt_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """你是一位專業的 AI 永續顧問，專門協助用戶查詢產品的 PCR (產品類別規則) 資料。
你的目標是根據用戶的查詢，利用提供的工具查找相關 PCR 資訊，並以專業、清晰、自然的語氣回覆用戶。

請嚴格遵守以下對話策略：

1.  **理解用戶意圖**：仔細分析用戶的輸入。判斷他們是想查詢產品、澄清資訊，還是有其他需求。
2.  **查詢產品資訊**：
    * 當用戶提供產品名稱、CCC Code 或任何看似產品查詢的內容時，你應該使用 `pcr_database_search` 工具來查詢資料庫。
    * **在呼叫工具前，請盡可能從用戶輸入中提取最精確的關鍵字作為 `query` 參數。** 例如，如果用戶說「我想查手機的 PCR」，`query` 應該是「手機」。
    * **如果用戶的查詢太過籠統或模糊 (例如：僅僅是「你好」、「幫我查」等)，請先禮貌地詢問他們想要查詢的具體產品名稱或 CCC Code。**
3.  **處理工具查詢結果**：
    * **如果 `pcr_database_search` 返回了多條記錄**：
        * 請向用戶簡要列出這些記錄的文件名稱和登錄編號（例如，列出前2-3條最相關的）。
        * 詢問用戶哪一條是他們感興趣的，或者是否需要你提供更詳細的資訊。
        * 提示用戶可以提供更精確的關鍵字（如完整的產品名稱或 CCC Code）來獲得更精準的結果。
    * **如果 `pcr_database_search` 返回了單條記錄**：
        * 請向用戶提供以下關鍵資訊：文件名稱、登錄編號、制定者、適用產品範圍簡述，以及完整的下載連結。
        * 詢問他們是否需要進一步的詳細資訊或協助（例如，解釋 PCR 內容、協助理解適用範圍，或查詢其他產品）。
    * **如果 `pcr_database_search` 沒有找到任何資料**：
        * 請禮貌地告知用戶結果（例如：「很抱歉，我們未能在資料庫中找到您所查詢產品的 PCR 資料。」）。
        * 詢問他們是否需要查詢其他產品，或提供其他形式的協助（例如，如果產品沒有 PCR，可以提供手動評估服務）。
    * **如果工具執行失敗**：
        * 告知用戶系統發生錯誤，請稍後再試。

請始終保持專業、樂於助人且自然的對話風格。
""",
        ),
        MessagesPlaceholder(variable_name="chat_history"),  # 引入對話歷史
        ("user", "{input}"),  # 用戶的當前輸入
        MessagesPlaceholder(
            variable_name="agent_scratchpad"
        ),  # Agent 內部思考和工具呼叫的痕跡
    ]
)


@router.post("/webhook")
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
            user_message = event["message"]["text"].strip()
            reply_token = event["replyToken"]
            user_id = event["source"]["userId"]

            logger.info(f"收到用戶 '{user_id}' 的訊息: '{user_message}'")

            # 獲取或初始化用戶的會話記憶和 Agent 執行器
            if user_id not in user_sessions:
                memory = ConversationBufferMemory(
                    memory_key="chat_history", return_messages=True
                )
                # 創建 Agent
                agent = create_openai_tools_agent(llm, tools, agent_prompt_template)
                # 創建 Agent 執行器
                agent_executor = AgentExecutor(
                    agent=agent,
                    tools=tools,
                    verbose=True,  # 設置為 True 可以看到 Agent 的思考過程，有利於調試
                    handle_parsing_errors=True,  # 處理 Agent 輸出解析錯誤
                )
                user_sessions[user_id] = {
                    "memory": memory,
                    "agent_executor": agent_executor,
                }

            session = user_sessions[user_id]
            memory = session["memory"]
            agent_executor = session["agent_executor"]

            logger.info(f"用戶 '{user_id}' 正在與 Agent 互動。")

            try:
                # 將用戶訊息加入記憶體 (在 Agent 處理前)
                memory.chat_memory.add_user_message(user_message)

                # 呼叫 Agent 執行器
                # Agent 會根據用戶輸入和對話歷史，決定是否使用工具，然後生成回應
                agent_response = await agent_executor.ainvoke(
                    {
                        "input": user_message,
                        "chat_history": memory.chat_memory.messages,  # 傳遞對話歷史
                    }
                )

                bot_reply_message = agent_response["output"]
                logger.info(f"Agent 回覆: {bot_reply_message}")

                # 將 Agent 的回覆加入記憶體 (在 Agent 處理後)
                memory.chat_memory.add_ai_message(bot_reply_message)

            except Exception as e:
                logger.error(f"Agent 執行失敗: {e}")
                bot_reply_message = "抱歉，AI 服務目前無法回應，請稍後再試。"
                # 即使 Agent 失敗，也要將錯誤回覆加入記憶體，保持對話連貫性
                memory.chat_memory.add_ai_message(bot_reply_message)

            await reply_line(reply_token, [{"type": "text", "text": bot_reply_message}])
        else:
            logger.info(f"收到非文本訊息或非訊息事件，類型: {event.get('type')}")

    return "OK"
