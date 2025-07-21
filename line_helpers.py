# line_helpers.py (這是概念上的獨立檔案)
import os
import httpx
import logging
from dotenv import load_dotenv
# 加載環境變量
load_dotenv()

# 再次配置日誌，確保此模組的日誌也能被記錄
logger = logging.getLogger(__name__)

# 檢查 LINE_CHANNEL_ACCESS_TOKEN 是否存在
# 在實際多檔案環境中，這部分可能會放在一個共享的配置檔或初始化腳本中
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
if not LINE_CHANNEL_ACCESS_TOKEN:
    logger.error("環境變量 'LINE_CHANNEL_ACCESS_TOKEN' 未設置。請檢查 .env 文件。")
    # 在實際部署中，您可能需要在此處退出或拋出異常
    # raise ValueError("LINE_CHANNEL_ACCESS_TOKEN is not set.")

async def reply_line(reply_token: str, messages: list):
    """
    發送訊息到 LINE 回覆 API。
    Args:
        reply_token (str): LINE 平台提供的回覆令牌。
        messages (list): 要發送的訊息列表。
    """
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("無法回覆 LINE：LINE_CHANNEL_ACCESS_TOKEN 未設置。")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    data = {"replyToken": reply_token, "messages": messages}
    
    logger.info(f"準備向 LINE API 發送回覆。reply_token: {reply_token[:10]}...")
    logger.debug(f"發送數據: {data}")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.line.me/v2/bot/message/reply",
                headers=headers,
                json=data,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"LINE API 回覆成功，狀態碼: {response.status_code}")
            logger.debug(f"LINE API 回應內容: {response.text}")
        except httpx.TimeoutException:
            logger.error("回覆 LINE API 超時。")
        except httpx.RequestError as e:
            logger.error(f"回覆 LINE API 請求錯誤: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"回覆 LINE API 失敗，HTTP 狀態碼: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logger.error(f"回覆 LINE 發生未知錯誤: {e}")
