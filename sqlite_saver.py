import sqlite3
import logging
import json  # 引入 json 模組以讀取 JSON 檔案

logger = logging.getLogger(__name__)


def save_to_sqlite(
    db_name: str = "pcr_list.db", json_file: str = "pcr_list_scraped.json"
):
    """
    將 PCR 數據從 JSON 檔案儲存到 SQLite 資料庫。
    Args:
        db_name (str): SQLite 資料庫檔案名稱。
        json_file (str): 包含 PCR 數據的 JSON 檔案名稱。
    """
    conn = None
    try:
        # 讀取 JSON 檔案
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"成功從 '{json_file}' 載入 {len(data)} 條記錄。")
        except FileNotFoundError:
            logger.error(f"錯誤: 未找到 JSON 檔案 '{json_file}'。請確認檔案是否存在。")
            return
        except json.JSONDecodeError:
            logger.error(
                f"錯誤: 無法解析 JSON 檔案 '{json_file}'。請確認檔案格式正確。"
            )
            return
        except Exception as e:
            logger.error(f"讀取 JSON 檔案時發生未知錯誤: {e}")
            return

        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # 建立表格，如果它不存在。
        # pcr_reg_no 作為主鍵，用於處理重複數據，如果插入的 pcr_reg_no 已存在，則更新現有記錄。
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pcr_records (
                pcr_reg_no TEXT PRIMARY KEY,
                pcr_source_type TEXT,
                document_name TEXT,
                developer TEXT,
                version TEXT,
                approval_date TEXT,
                effective_date TEXT,
                product_scope TEXT,
                download_link TEXT,
                feedback_link TEXT,
                ccc_codes TEXT
            )
        """
        )
        conn.commit()
        logger.info(
            f"SQLite 資料庫 '{db_name}' 已建立或已存在，表格 'pcr_records' 已準備就緒。"
        )

        # 準備插入數據的 SQL 語句
        # 使用 INSERT OR REPLACE 可以在遇到主鍵衝突時更新現有記錄，避免重複插入
        insert_sql = """
            INSERT OR REPLACE INTO pcr_records (
                pcr_reg_no, pcr_source_type, document_name, developer, version,
                approval_date, effective_date, product_scope, download_link,
                feedback_link, ccc_codes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # 遍歷數據並插入到資料庫
        for entry in data:
            try:
                # 將字典中的值按照 SQL 語句的順序提取
                # 確保所有鍵都存在，否則提供空字串作為預設值
                values = (
                    entry.get("pcr_reg_no", ""),
                    entry.get("pcr_source_type", ""),
                    entry.get("document_name", ""),
                    entry.get("developer", ""),
                    entry.get("version", ""),
                    entry.get("approval_date", ""),
                    entry.get("effective_date", ""),
                    entry.get("product_scope", ""),
                    entry.get("download_link", ""),
                    entry.get("feedback_link", ""),
                    entry.get("ccc_codes", ""),
                )
                cursor.execute(insert_sql, values)
            except sqlite3.Error as e:
                logger.error(
                    f"插入數據時發生錯誤 (PCR 登錄編號: {entry.get('pcr_reg_no', 'N/A')}): {e}"
                )

        conn.commit()  # 提交所有變更
        logger.info(f"所有 PCR 數據已成功儲存到 '{db_name}'。")

    except sqlite3.Error as e:
        logger.error(f"SQLite 資料庫操作失敗: {e}")
    finally:
        if conn:
            conn.close()  # 確保關閉資料庫連線
            logger.info("SQLite 資料庫連線已關閉。")


if __name__ == "__main__":
    logger.info("正在執行 sqlite_saver.py 的獨立測試...")
    save_to_sqlite(db_name="pcr_list.db")
    logger.info("sqlite_saver.py 獨立測試完成。請檢查 'test_pcr_list.db' 檔案。")
