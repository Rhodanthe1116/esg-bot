import os
import json
import re
from typing import Dict, List, Any

# --- 設定 ---
JSON_FILE = "pcr_list_scraped.json"


def extract_fid_from_link(link: str) -> str:
    """
    從 download_link 參數中提取唯一的 FID 識別碼。
    FID 格式假設為 GUID-YY-NNN (例如: ...-23-015)。
    """
    print(f"正在處理連結: {link}")
    fid_match = re.search(r"fid=([^&]+)", link)
    if not fid_match:
        raise ValueError(f"在連結中找不到 fid 參數: {link}")

    fid_param_value = fid_match.group(1)
    print(f"提取到的 fid 參數值: {fid_param_value}")

    # 尋找 FID 結尾 (-XX-YYY)，它位於 GUID 之後，文件編碼名稱之前
    # 正則表達式匹配: ([GUID]-[YY]-[NNN])[+-][Encoded Filename...]
    match = re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        fid_param_value,
        re.IGNORECASE,
    )
    print(f"正則表達式匹配結果: {match}")

    if match:
        return match.group(0)

    # 如果找不到標準格式，返回 "NoFID"
    raise  ValueError(f"無法從 fid 參數中提取 FID: {fid_param_value}")


def update_json_with_fid():
    """載入 JSON 數據，提取並添加 FID 欄位，然後將數據儲存回原始檔案。"""

    if not os.path.exists(JSON_FILE):
        print(f"錯誤：找不到檔案: {JSON_FILE}。請確認檔案路徑是否正確。")
        return

    try:
        # 1. 載入數據
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data: List[Dict[str, Any]] = json.load(f)

        print(f"成功載入 {len(data)} 筆數據。開始處理...")

        processed_count = 0

        # 2. 處理數據並添加 fid
        for item in data:
            download_link = item.get("download_link")

            if download_link:
                # 提取 FID
                fid = extract_fid_from_link(download_link)

                # 添加新的 fid 欄位
                item["fid"] = fid
                processed_count += 1
            else:
                # 如果沒有 download_link，則將 fid 設為 "NoLink"
                item["fid"] = "NoLink"

        # 3. 儲存修改後的數據
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            # 使用 indent=4 讓 JSON 文件保持美觀易讀
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"\n成功處理並更新 {processed_count} 筆數據。")
        print(f"檔案 {JSON_FILE} 已更新完成。")

    except json.JSONDecodeError:
        print(f"錯誤：檔案 {JSON_FILE} 不是有效的 JSON 格式。")
    except Exception as e:
        print(f"處理檔案時發生未預期的錯誤: {e}")


if __name__ == "__main__":
    update_json_with_fid()
