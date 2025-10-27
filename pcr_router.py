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
import json
from pathlib import Path

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


@router.get(
    "/by_reg_no",
    response_model=PCRRecord,
    summary="依 PCR 登錄編號查詢單筆記錄",
    description="從本地 pcr_list_scraped.json 中以 pcr_reg_no 精確比對並回傳該筆記錄。",
)
async def get_pcr_record_by_reg_no(pcr_reg_no: str = Query(..., description="PCR 登錄編號，例如 24-011")):
    """
    直接從本地的 `pcr_list_scraped.json` 檔案中尋找與 `pcr_reg_no` 完全相符的記錄並回傳。
    若找不到，回傳 404。
    """
    try:
        # 檔案相對於此模組所在路徑
        base = Path(__file__).resolve().parent
        json_path = base.joinpath("pcr_list_scraped.json")

        # 如果在同層找不到，嘗試專案根目錄
        if not json_path.exists():
            json_path = base.parent.joinpath("pcr_list_scraped.json")

        if not json_path.exists():
            logger.error(f"找不到 pcr_list_scraped.json (checked {json_path})")
            raise HTTPException(status_code=500, detail="伺服器尚未載入 PCR 資料 (pcr_list_scraped.json 不存在)")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 資料可能是列表
        if not isinstance(data, list):
            logger.error("pcr_list_scraped.json 格式錯誤，預期為 list")
            raise HTTPException(status_code=500, detail="pcr_list_scraped.json 格式錯誤")

        # 精確比對 pcr_reg_no，忽略大小寫與前後空白
        target = (pcr_reg_no or "").strip().lower()
        for entry in data:
            entry_reg = (entry.get("pcr_reg_no") or "").strip().lower()
            if entry_reg == target:
                # 返回 PCRRecord，允許部分欄位缺失
                try:
                    return PCRRecord(**entry)
                except Exception:
                    # 若 entry 包含多餘鍵，僅挑出 PCRRecord 欄位
                    allowed = {k: v for k, v in entry.items() if k in PCRRecord.__fields__}
                    return PCRRecord(**allowed)

        # 找不到
        raise HTTPException(status_code=404, detail=f"找不到 PCR 記錄: {pcr_reg_no}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查詢單筆 PCR 發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"伺服器錯誤: {e}")
