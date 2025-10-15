import logging
from fastapi import APIRouter, Depends, HTTPException, Query  # 引入 APIRouter
from typing import List, Optional
from langchain_community.vectorstores import Chroma

from chroma_manager import get_chroma_db
from pcr_services import (
    get_pcr_records_from_chroma,
    get_pcr_records_from_db,
    PCRRecord,
)  # 從 pcr_services.py 匯入服務函數和模型

# 配置日誌
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 創建 APIRouter 實例
router = APIRouter(
    prefix="/pcr_records",  # 為所有此路由中的端點設定共同前綴
    tags=["PCR Records"],  # 在 Swagger UI 中分組
    # summary="PCR記錄查詢", # 移除此行，APIRouter.__init__() 不接受 'summary'
    # description="用於查詢環境部產品碳足跡PCR記錄的API端點。" # 移除此行，APIRouter.__init__() 不接受 'description'
)


@router.get(
    "/",  # 這裡的 "/" 會與 router 的 prefix 合併，形成 "/pcr_records/"
    response_model=List[PCRRecord],
    summary="查詢所有PCR記錄",  # summary 和 description 應該放在這裡
    description="從資料庫中獲取所有 PCR 記錄，支援分頁和關鍵字搜尋。",  # summary 和 description 應該放在這裡
)
async def get_pcr_records(
    skip: int = Query(0, ge=0, description="跳過的記錄數 (Offset)"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大記錄數 (Limit)"),
    search: Optional[str] = Query(
        None, description="在文件名稱、制定者或產品範圍中搜尋的關鍵字"
    ),
    chroma: Chroma = Depends(get_chroma_db),
):
    """
    獲取 PCR 記錄列表。
    - **skip**: 跳過指定數量的記錄（用於分頁）。
    - **limit**: 限制返回的記錄數量。
    - **search**: 在 'document_name', 'developer', 'product_scope' 欄位中進行模糊搜尋。
    """
    try:
        # 呼叫服務層的函數來獲取數據
        records = await get_pcr_records_from_chroma(chroma, skip=skip, limit=limit, search=search)
        # records = await get_pcr_records_from_db(skip=skip, limit=limit, search=search)
        return records
    except Exception as e:
        logger.error(f"API 路由層錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")
