from langchain.docstore.document import Document
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import SentenceTransformerEmbeddings
import json
import os

# --- 設定 ---
JSON_FILE = "pcr_list_scraped.json"
CHROMA_PATH = "./chroma_json_store"
MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"  # 適合中文的多語言嵌入模型

# --- 數據處理函數 ---


def load_json_data(file_path: str) -> list:
    """從 JSON 檔案中讀取數據"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到檔案: {file_path}。請確保檔案存在。")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"成功讀取 {len(data)} 個數據項目。")
    return data


from langchain.docstore.document import Document
from typing import List, Dict, Any


def json_to_documents(data: List[Dict[str, Any]]) -> List[Document]:
    """
    將 JSON 數據清單轉換為 LangChain Document 物件清單。

    【優化點】：調整內容權重，將文件名稱 (document_name)
    與產品範圍 (product_scope) 結合，作為主要的向量化內容。
    """
    documents = []
    for item in data:
        # 提取關鍵欄位
        doc_name = item.get("document_name", "無文件名稱")
        product_scope = item.get("product_scope", "無產品範圍描述")

        # 設置主要內容 (page_content) - 調整權重
        # 將文件名稱放在最前面，並加上標籤，讓它成為最重要的語義錨點。
        content = f"文件名稱: {doc_name}。\n" f"產品適用範圍詳細描述: {product_scope}"

        # 設置元數據 (metadata) - 儲存所有欄位
        # 即使內容欄位已合併，元數據中仍保留所有原始欄位，方便結果展示和過濾。
        metadata = {k: v for k, v in item.items()}

        # 創建 Document
        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)
    return documents


# --- 範例測試 (假設您使用上面修改後的函數) ---
# 假設 json_data 已經載入

# 原始布丁文件的內容將變成類似這樣:
# content = "文件名稱: 布丁。\n產品適用範圍詳細描述: 以乳製品、雞蛋、食用性膠類等相關原料..."

# 原始調理蛋品的內容將變成類似這樣:
# content = "文件名稱: 調理蛋品與醃製蛋品。\n產品適用範圍詳細描述: 適用範圍包括國家標準CNS15147蛋類產品-總則所涵蓋之調理蛋品(Prepared Eggs)..."


# --- 核心邏輯 ---


def setup_db():

    # --- 步驟 2: 建立或載入嵌入模型和向量儲存 ---
    embeddings = SentenceTransformerEmbeddings(model_name=MODEL_NAME)

    if (
        not os.path.exists(CHROMA_PATH)
        or not Chroma(
            persist_directory=CHROMA_PATH, embedding_function=embeddings
        ).get()["ids"]
    ):
        print(">>> 建立新的向量索引...")
        # 第一次運行：存入 ChromaDB
        try:
            # --- 步驟 1: 讀取並轉換數據 ---
            json_data = load_json_data(JSON_FILE)
            documents = json_to_documents(json_data)
        except FileNotFoundError as e:
            print(f"錯誤：{e}")
            raise Exception("無法繼續，因為缺少必要的數據檔案。")

        db = Chroma.from_documents(documents, embeddings, persist_directory=CHROMA_PATH)
    else:
        print(">>> 載入已存在的向量索引...")
        # 後續運行：直接載入
        db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    return db
