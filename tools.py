import logging
from typing import List, Optional
from langchain_core.tools import tool  # 引入 tool 裝飾器

# 從 pcr_services.py 匯入實際的資料庫查詢函數和 PCRRecord 模型
from pcr_services import get_pcr_records_from_db, get_pcr_records_from_chroma, PCRRecord
from chroma_manager import chroma_manager, get_chroma_db

logger = logging.getLogger(__name__)


# 將 get_pcr_records_from_db 函數包裝成 LangChain Tool
# 使用 @tool 裝飾器，並提供清晰的名稱和描述
@tool
async def pcr_database_search(query: str) -> List[PCRRecord]:
    """
    用於查詢環境部產品碳足跡PCR資料庫的工具。
    根據產品名稱、CCC Code、制定者或產品範圍進行模糊搜尋。
    返回一個包含PCR記錄的列表。如果沒有找到，返回空列表。

    Args:
        query (str): 用戶提供的產品名稱、CCC Code 或其他相關搜尋關鍵字。

    Returns:
        List[PCRRecord]: 找到的PCR記錄列表。
    """
    logger.info(f"工具呼叫: pcr_database_search，查詢內容: '{query}'")
    try:
        # 呼叫 pcr_services 中的實際查詢函數
        # 將 limit 從 1 增加到 3，以便 Agent 可以處理多個結果
        records = await get_pcr_records_from_db(search=query, limit=3)
        logger.info(f"工具執行結果: 找到 {len(records)} 條記錄。")
        return records
    except Exception as e:
        logger.error(f"工具執行失敗: {e}")
        # 工具執行失敗時，返回一個空的 PCRRecord 列表或包含錯誤訊息的特殊對象
        # 讓 Agent 知道查詢失敗
        return (
            []
        )  # 或者返回 [PCRRecord(pcr_reg_no="ERROR", document_name=f"查詢失敗: {e}")]


@tool
async def pcr_chroma_search(query: str) -> List[PCRRecord]:
    """
    使用 Chroma 向量索引進行檔案級檢索的工具（RAG-style）。
    這會呼叫 `get_pcr_records_from_chroma`，返回最相關的 PCRRecord 列表。

    Args:
        query (str): 使用者的查詢文字，會用於向量相似度檢索。

    Returns:
        List[PCRRecord]: 按相關性排序的 PCR 記錄清單（可能為空）。
    """
    logger.info(f"工具呼叫: pcr_chroma_search，查詢內容: '{query}'")
    try:
        # 確保 ChromaDB 已初始化（在 main.py 啟動時通常已經初始化）
        if getattr(chroma_manager, "_db", None) is None:
            try:
                chroma_manager.initialize_db()
            except Exception as init_err:
                logger.error(f"初始化 ChromaDB 失敗: {init_err}")
                return []

        db = get_chroma_db()

        # 使用向量檢索服務查詢（將 limit 設為 3，以便 Agent 處理多個結果）
        records = await get_pcr_records_from_chroma(db, skip=0, limit=3, search=query)
        logger.info(f"工具執行結果: 在 Chroma 中找到 {len(records)} 條記錄。")
        return records
    except Exception as e:
        logger.exception(f"工具執行失敗 (Chroma): {e}")
        return []
