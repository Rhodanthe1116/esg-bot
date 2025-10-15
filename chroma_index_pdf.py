import os
import json
import re
from typing import Dict, List, Any
from langchain.text_splitter import RecursiveCharacterTextSplitter

# NOTE: 您需要安裝這些函式庫才能運行此腳本:
# pip install chromadb pypdf tqdm langchain-community sentence-transformers

# --- 設定 ---
PDF_FOLDER = "./pcr_pdfs"
JSON_FILE = "pcr_list_scraped.json"
CHROMA_DIR = "./chroma_db" # 向量資料庫儲存路徑
COLLECTION_NAME = "pcr_documents"
# 這是您在 chroma_manager.py 中使用的模型，索引和檢索必須保持一致！
MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

# --- 外部庫導入 ---
try:
    # 這裡只導入 LangChain 的 Chroma Wrapper
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import SentenceTransformerEmbeddings
    from pypdf import PdfReader
    from tqdm import tqdm
except ImportError:
    print("錯誤：請安裝必要的函式庫：pip install chromadb pypdf tqdm langchain-community sentence-transformers")
    exit()


def load_json_metadata(file_path: str) -> Dict[str, Any]:
    """
    載入 JSON 檔案並將其轉換為以 FID 為鍵的字典，方便查找。
    我們依賴於 'update_json_with_fid.py' 腳本已添加的 'fid' 欄位。
    鍵值格式：{fid: metadata_dict}
    """
    if not os.path.exists(file_path):
        print(f"錯誤：找不到檔案: {file_path}")
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    metadata_map = {}
    for item in data:
        fid = item.get("fid")
        if fid and fid != "NoFID" and fid != "NoLink":
            metadata_map[fid] = item

    print(f"成功載入 {len(metadata_map)} 筆 metadata (已使用 'fid' 欄位作為鍵)。")
    return metadata_map


def extract_fid_from_filename(filename: str) -> str:
    """
    從 PDF 檔名 '{fid}-{name}.pdf' 中提取 fid。
    fid 可能為純 GUID 或 GUID-YY-NNN 格式。
    """
    # 匹配檔名開頭的 GUID 或 GUID-YY-NNN
    guid_pattern = (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )

    # 匹配可能包含 -YY-NNN 後綴的 FID (例如: ...-23-015)
    fid_pattern = rf"^({guid_pattern})"

    match = re.search(fid_pattern, filename, re.IGNORECASE)

    if match:
        return match.group(1)

    return "NoFID"


def index_pdfs_to_chroma():
    """
    讀取 pcr_pdfs 資料夾中的 PDF 文件，提取內容和 metadata，並建立 Chroma 索引。
    """

    # 1. 載入 metadata (使用 FID 作為鍵)
    metadata_map = load_json_metadata(JSON_FILE)
    if not metadata_map:
        return

    # 2. 初始化嵌入模型 (與 chroma_manager.py 保持一致)
    embeddings = SentenceTransformerEmbeddings(model_name=MODEL_NAME)
    print(f"[{os.getpid()}] 正在使用嵌入模型: {MODEL_NAME}")

    # 3. 初始化 Chroma 客戶端 (使用 LangChain Wrapper)
    # 這個 Wrapper 會處理嵌入函數的正確傳遞和初始化。
    db = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,  # 傳入嵌入函數實例
        persist_directory=CHROMA_DIR,
    )
    print(f"Chroma 客戶端已初始化，資料庫路徑: {CHROMA_DIR}")

    # 4. 處理 PDF 文件
    pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.endswith(".pdf")]
    print(f"找到 {len(pdf_files)} 個 PDF 文件準備索引...")
    
    # pdf_files = pdf_files[:5]

    documents = []
    metadatas = []
    ids = []
    doc_count = 0

    for filename in tqdm(pdf_files, desc="索引進度"):
        file_path = os.path.join(PDF_FOLDER, filename)

        try:
            # 5. 從檔名中解析 FID (與 JSON 鍵一致)
            fid = extract_fid_from_filename(filename)

            if fid == "NoFID":
                # 這裡可能需要處理檔名不符合 GUID 或 GUID-YY-NNN 格式的情況
                print(f"\n警告：檔名格式不符，無法提取 FID: {filename}")
                continue

            metadata = metadata_map.get(fid)
            if not metadata:
                print(
                    f"\n警告：找不到 FID {fid} 的 JSON metadata。跳過文件：{filename}"
                )
                continue

            # 替換原有的 PDF 讀取和分塊步驟 (第 6 步)
            # --- 6. 讀取 PDF 內容並分塊 ---
            reader = PdfReader(file_path)
            text_content = ""
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    # 移除頁碼和標題的頁面級上下文，讓切割器專注於內容
                    text_content += page_text + "\n\n"

            if not text_content:
                print(f"\n警告：文件 {filename} 內容為空或無法提取文本。跳過。")
                continue

            
            # *** 使用更穩健的文本切割器 ***
            text_splitter = RecursiveCharacterTextSplitter(
                # 常見的 RAG 參數：
                chunk_size=1000, 
                chunk_overlap=200, # 保持塊之間有 200 字元的重疊來保留上下文
                separators=["\n\n", "\n", " ", ""], # 按優先級嘗試這些分隔符
                length_function=len,
                is_separator_regex=False,
            )

            # 使用切割器來處理整個文檔的文本
            chunks = text_splitter.split_text(text_content)

            # 過濾掉可能因為邊緣情況產生的小塊
            chunks = [chunk for chunk in chunks if len(chunk.strip()) > 50]

            # --- 7. 準備索引數據 ---
            for i, chunk in enumerate(chunks):
                # 每個塊的唯一 ID
                chunk_id = f"{fid}-{i}"

                # 複製 JSON 中的所有 metadata 到每個文本塊
                chunk_metadata = {
                    "fid": fid,
                    "downloaded_filename": filename,
                    "chunk_index": i,
                    **metadata, # 包含 JSON 中所有原始 metadata (pcr_source_type, developer, document_name, etc.)
                }

                documents.append(chunk)
                metadatas.append(chunk_metadata)
                ids.append(chunk_id)
                doc_count += 1

        except Exception as e:
            # 這裡捕獲到您的錯誤，並會顯示出來
            print(f"\n錯誤：處理文件 {filename} 時發生未預期的錯誤: {e}")
            continue

    # 8. 加入到 Chroma 集合中 (使用 LangChain Wrapper 的 add_texts)
    if documents:
        # LangChain's add_texts 方法會自動使用我們在步驟 3 傳入的 embeddings 函數進行嵌入。
        db.add_texts(texts=documents, metadatas=metadatas, ids=ids)

        print(
            f"\n成功將 {doc_count} 個文本塊添加到 Chroma 索引 '{COLLECTION_NAME}' 中。"
        )
    else:
        print("\n沒有可索引的文本塊。")


if __name__ == "__main__":
    # 在運行前，請確保刪除舊的 './chroma_db' 資料夾，以避免模型不一致的衝突。
    if not os.path.exists(PDF_FOLDER):
        print(f"錯誤：找不到 PDF 資料夾: {PDF_FOLDER}。請確認您的 PDF 文件已儲存。")
    else:
        index_pdfs_to_chroma()
