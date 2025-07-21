import sqlite3
import logging
from fastapi import HTTPException

# 配置日誌
logger = logging.getLogger(__name__)

# 資料庫檔案名稱
DATABASE_FILE = "pcr_list.db"


def get_db_connection():
    """
    建立並返回一個 SQLite 資料庫連線。
    連線會設定為 row_factory，讓查詢結果可以像字典一樣存取。
    """
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row  # 讓查詢結果可以像字典一樣存取
        return conn
    except sqlite3.Error as e:
        logger.error(f"無法連接到資料庫 '{DATABASE_FILE}': {e}")
        # 在 FastAPI 應用程式中拋出 HTTPException
        raise HTTPException(status_code=500, detail="無法連接到資料庫")
