import sqlite3
import logging
from typing import List, Optional
from pydantic import BaseModel  # 引入 BaseModel 以便在服務層定義返回模型

from db import get_db_connection  # 從 db.py 匯入資料庫連線函數
from pcr_models import PCRRecord  # 從 pcr_models.py 匯入 PCRRecord 模型

logger = logging.getLogger(__name__)

# PCRRecord 模型現在從 pcr_models.py 匯入，因此這裡不再需要重複定義。
# class PCRRecord(BaseModel):
#     pcr_reg_no: str
#     pcr_source_type: Optional[str]
#     document_name: Optional[str]
#     developer: Optional[str]
#     version: Optional[str]
#     approval_date: Optional[str]
#     effective_date: Optional[str]
#     product_scope: Optional[str]
#     download_link: Optional[str]
#     feedback_link: Optional[str]
#     ccc_codes: Optional[str]


async def get_pcr_records_from_db(
    skip: int = 0, limit: int = 100, search: Optional[str] = None
) -> List[PCRRecord]:
    """
    從資料庫中獲取 PCR 記錄列表。
    這個函數包含了實際的資料庫查詢邏輯，可以被多個地方重複使用。
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM pcr_records"
        params = []
        where_clauses = []

        if search:
            search_term_lower = f"%{search.lower()}%"
            where_clauses.append(
                "(LOWER(document_name) LIKE ? OR LOWER(developer) LIKE ? OR LOWER(product_scope) LIKE ?)"
            )
            params.extend([search_term_lower, search_term_lower, search_term_lower])

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, skip])

        logger.info(f"執行服務層查詢: {query}，參數: {params}")
        cursor.execute(query, params)
        records = cursor.fetchall()

        # 將查詢結果轉換為 PCRRecord 模型列表
        return [PCRRecord(**record) for record in records]

    except sqlite3.Error as e:
        logger.error(f"服務層資料庫查詢失敗: {e}")
        # 這裡不直接拋出 HTTPException，而是拋出普通的 Exception，
        # 讓上層 (router) 決定如何處理 HTTP 錯誤
        raise Exception(f"資料庫查詢失敗: {e}")
    finally:
        if conn:
            conn.close()
            logger.info("服務層資料庫連線已關閉。")
