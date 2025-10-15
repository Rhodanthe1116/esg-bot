import os
import json
import requests
from typing import List, Dict, Any
import re

# 由於 urllib.parse 才是真正需要的，我們明確引入
import urllib.parse
from email.message import Message

# --- 設定 ---
JSON_FILE = "pcr_list_scraped.json"
PDF_FOLDER = "./pcr_pdfs"  # PDF 文件儲存資料夾
# 您提供的下載連結基礎 URL
DOWNLOAD_BASE_URL = "https://cfp-calculate.tw/cfpc/Carbon/WebPage/"


# --- 輔助函數：載入 JSON 數據 ---
def load_json_data(file_path: str) -> List[Dict[str, Any]]:
    """從 JSON 檔案中讀取數據"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到檔案: {file_path}。請確保檔案存在。")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"成功讀取 {len(data)} 個數據項目。")
    return data


def extract_fid_from_link(link: str) -> str:
    """從 download_link 欄位中提取 fid"""
    # 確保 fid 參數可以被正確提取
    match = re.search(r"fid=([^&]+)", link)
    return match.group(1) if match else "NoFID"


def get_filename_from_response(response: requests.Response) -> str:
    """
    【最終優化】從 Content-Disposition 標頭中解析出原始文件名，
    並加入 Latin-1 到 UTF-8 的編碼修正，以解決中文亂碼問題。
    """
    cd = response.headers.get("Content-Disposition")

    # 預設文件名（如果找不到任何標頭信息）
    filename = "downloaded_file.pdf"

    if not cd:
        # 如果 Content-Disposition 標頭不存在，嘗試從 URL 結尾獲取文件名
        url_path = urllib.parse.urlparse(response.url).path
        filename = os.path.basename(url_path) or filename
    else:
        parsed_filename = None
        try:
            # --- 嘗試 1: 使用 email.message 進行標準解析 ---
            # email 模組能自動處理 filename 和 filename* (RFC 5987) 編碼
            msg = Message()
            msg["Content-Disposition"] = cd
            parsed_filename = msg.get_filename()

            if parsed_filename:
                # 對解析後的結果進行 URL 解碼 (處理可能殘留的 %xx 或 +)
                filename = urllib.parse.unquote(parsed_filename)

        except Exception as e:
            # print(f"警告：email.message 解析失敗: {e}")
            pass  # 繼續執行備份邏輯

        # --- 嘗試 2: 手動解析與編碼修正 (解決亂碼的關鍵) ---
        # 僅在 email.message 沒有得到有效文件名時執行
        if not parsed_filename:
            # 匹配 filename 或 filename*
            match = re.search(r'filename\*?=(?:utf-8\'\'|")?([^;"]+)', cd, re.I)
            if match:
                raw_value = match.group(1).strip("'\"")

                # 1. 嘗試 URL 解碼 (處理 %xx 編碼)
                decoded_value = urllib.parse.unquote(raw_value)

                # 2. 嘗試 Latin-1 -> UTF-8 修正
                # requests 預設以 Latin-1 解碼 header，若伺服器發送 UTF-8 會導致亂碼。
                # 這裡將 Latin-1 亂碼字符串 '還原' 為原始 bytes，再用 UTF-8 解碼。
                try:
                    filename = decoded_value.encode("iso-8859-1").decode(
                        "utf-8", errors="strict"
                    )
                except (UnicodeEncodeError, UnicodeDecodeError):
                    # 如果修正失敗，則使用 URL 解碼後的結果
                    filename = decoded_value

    # 確保文件名以 .pdf 結尾（如果伺服器回傳的文件名沒有擴展名）
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    # 清理文件名中的非法字符 (避免操作系統錯誤)
    # 刪除所有不允許的字符
    safe_filename = re.sub(r'[\\/:*?"<>|]', "", filename)

    return safe_filename.strip()


# --- 核心下載函數 ---
def download_pdfs_from_json():
    """載入 JSON 數據並下載所有相關的 PDF 文件"""

    try:
        data = load_json_data(JSON_FILE)
    except FileNotFoundError as e:
        print(f"錯誤：{e}")
        return

    os.makedirs(PDF_FOLDER, exist_ok=True)
    print(f"PDF 文件將儲存到: {PDF_FOLDER}")

    success_count = 0
    fail_count = 0

    for item in data:
        document_name = item.get("document_name", "untitled")
        download_link_suffix = item.get("download_link")

        if not download_link_suffix:
            print(f"    [跳過] '{document_name}': 缺少 download_link 欄位。")
            fail_count += 1
            continue

        full_url = f"{DOWNLOAD_BASE_URL}{download_link_suffix}"

        # 1. 提取 fid 作為文件名前綴
        fid_prefix = extract_fid_from_link(download_link_suffix)

        # 2. 下載並獲取原始文件名
        print(f"    [下載中] '{document_name}' (FID: {fid_prefix})...")
        try:
            # 必須使用 stream=True 並且不能立即下載全部內容，才能先讀取 Content-Disposition 標頭
            response = requests.get(full_url, stream=True, timeout=30)
            response.raise_for_status()

            # 從伺服器響應中解析出原始文件名
            original_filename = get_filename_from_response(response)

            # 3. 構建最終文件名: {fid}-{原始文件名}
            final_filename = f"{fid_prefix}-{original_filename}"
            file_path = os.path.join(PDF_FOLDER, final_filename)

            if os.path.exists(file_path):
                print(f"    [存在] '{document_name}' 已下載。跳過。")
                success_count += 1
                continue

            # 4. 寫入文件
            with open(file_path, "wb") as pdf_file:
                for chunk in response.iter_content(chunk_size=8192):
                    pdf_file.write(chunk)

            print(f"    [成功] 下載並儲存為: {final_filename}")
            success_count += 1

        except requests.exceptions.RequestException as e:
            status_code = getattr(e.response, "status_code", "N/A")
            print(
                f"    [失敗] 下載 '{document_name}' (Status: {status_code}) 失敗: {e}"
            )
            fail_count += 1
        except Exception as e:
            print(f"    [失敗] 處理 '{document_name}' 時發生錯誤: {e}")
            fail_count += 1

    print("\n--- 下載總結 ---")
    print(f"成功下載/已存在: {success_count} 筆")
    print(f"下載失敗/跳過: {fail_count} 筆")


if __name__ == "__main__":
    download_pdfs_from_json()
