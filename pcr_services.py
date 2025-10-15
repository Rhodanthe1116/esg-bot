import sqlite3
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel  # 引入 BaseModel 以便在服務層定義返回模型
from langchain_community.vectorstores import Chroma
from langchain.docstore.document import Document
from collections import Counter

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


async def get_pcr_records_from_chroma(
    db: Chroma,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    k_chunks_initial: int = 100,  # 初次檢索的文本塊數量 K
    top_n_documents: int = 10,  # 最終要返回的最相關文件數量 N
) -> List[PCRRecord]:
    """
    執行文件級 RAG 檢索。首先定位最相關的 Top N 文件，並僅使用首次檢索到的相關文本塊作為上下文。

    此版本移除了二次資料庫呼叫 (db.get)，提高查詢效率，並使用 fid 作為文件識別碼。
    """
    if not search:
        logger.warning("未提供搜索查詢。")
        return []

    try:
        # 步驟 1: 檢索最相關的 K 個文本塊 (Chunk)，作為定位文件的訊號和上下文來源
        initial_chunks = db.similarity_search(search, k=k_chunks_initial)

        if not initial_chunks:
            logger.info(f"查詢 '{search}' 未找到任何相關文本塊。")
            return []

        # 步驟 2: 匯總並篩選出最相關的 Top N 個文件 ID (fid)
        top_doc_fids = get_top_n_document_fids(initial_chunks, top_n_documents)

        # 步驟 3: 聚合內容並轉換為 PCRRecord 輸出格式 (僅使用 initial_chunks 中的內容)

        # document_context 現在以 fid 作為鍵 (key)
        document_context: Dict[str, PCRRecord] = {}

        # 僅遍歷首次檢索到的文本塊
        for chunk in initial_chunks:
            fid = chunk.metadata.get("fid")

            # 僅處理屬於 Top N 文件的文本塊
            if fid and fid in top_doc_fids:
                # 初始化文件結構並累積文本塊內容
                if fid not in document_context:
                    document_context[fid] = PCRRecord(
                        **chunk.metadata,  # 保留所有原始 metadata
                        page_contents=[],
                    )

                # 將該文本塊的內容加入上下文
                document_context[fid].page_contents.append(chunk.page_content)

        # 步驟 4: 轉換為最終的 PCRRecord 列表 (保持 Top N 的排名順序)
        final_records: List[PCRRecord] = []

        # 依照排名順序 (top_doc_fids) 建立輸出記錄
        for i, fid in enumerate(top_doc_fids):
            if fid in document_context:
                record = document_context[fid]

                # 將所有文本塊內容用分隔符合併成一個長字符串，供 LLM 使用
                full_context = "\n\n--- 文件內文本塊分隔線 ---\n\n".join(
                    record.page_contents
                )
                record.page_content = full_context  # 將聚合內容存入 page_content 欄位

                # 建立 PCRRecord 實例 (包含聚合的上下文)
                final_records.append(record)

                # 輸出確認資訊
                print(f"【結果 {i+1} - 文件級 (僅首次檢索內容)】 文件 ID (fid): {fid}")
                print(f"  文件名: {record.document_name}")
                print(f"  已合併 {len(record.page_contents)} 個首次檢索到的文本塊")
                print(f"  開發者: {record.developer}")
                print("-" * 20)
            else:
                logger.warning(
                    f"文件 ID '{fid}' 在聚合步驟中丟失，可能是因為在 initial_chunks 中沒有足夠的 metadata。"
                )

        logger.info(
            f"成功為查詢 '{search}' 處理並返回 {len(final_records)} 個文件級記錄。"
        )
        return final_records

    except Exception as e:
        logger.error(f"服務層資料庫查詢失敗: {e}")
        # 拋出普通的 Exception，讓上層 (router) 決定如何處理 HTTP 錯誤
        raise Exception(f"資料庫查詢失敗: {e}")
    finally:
        pass


def get_top_n_document_fids(chunks: List[Document], top_n: int) -> List[str]:
    """
    從檢索到的文本塊列表中，計算哪個文件的 document_name 出現的次數最多，
    並返回得分最高的前 N 個獨特的 document_name 列表 (FID)。
    """
    # 1. 提取 document_name (模擬 fid)
    fids = [doc.metadata.get("fid") for doc in chunks if doc.metadata.get("fid")]

    # 2. 計算每個文件的出現頻率。頻率越高，相關性越高。
    fid_counts = Counter(fids)

    # 3. 根據計數降序排序，並取前 top_n
    top_ids_with_counts = fid_counts.most_common(top_n)

    # 4. 提取 document_name
    top_fids = [fid for fid, count in top_ids_with_counts]

    logger.info(f"從 {len(fids)} 個文本塊中，成功篩選出 Top {top_n} 個文件: {top_fids}")

    return top_fids
