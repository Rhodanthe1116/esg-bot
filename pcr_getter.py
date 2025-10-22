import os
import json
import re
from typing import Dict, List, Any

# --- 設定 ---
JSON_FILE = "pcr_list_scraped.json"


def get_names():
    """載入 JSON 數據"""

    if not os.path.exists(JSON_FILE):
        print(f"錯誤：找不到檔案: {JSON_FILE}。請確認檔案路徑是否正確。")
        return

    try:
        # 1. 載入數據
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data: List[Dict[str, Any]] = json.load(f)

        print(f"成功載入 {len(data)} 筆數據。開始處理...")

        # 2. 取得每項的 document_name 並存成 list（只保留非空字串）
        document_names: List[str] = [
          item.get("document_name") for item in data
          if isinstance(item, dict) and item.get("document_name")
        ]

        print(f"已取得 {len(document_names)} 個 document_name。")

        for name in document_names:
            print(name)
    except json.JSONDecodeError:
        print(f"錯誤：檔案 {JSON_FILE} 不是有效的 JSON 格式。")
    except Exception as e:
        print(f"處理檔案時發生未預期的錯誤: {e}")


if __name__ == "__main__":
    get_names()
