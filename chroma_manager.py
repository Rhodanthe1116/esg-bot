import os
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import SentenceTransformerEmbeddings

# --- 設定 ---


MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

# CHROMA_PATH = "./chroma_json_store"

CHROMA_PATH = "./chroma_db"  # 必須與 create_chroma_index.py 中的 CHROMA_DIR 一致
COLLECTION_NAME = (
    "pcr_documents"  # 必須與 create_chroma_index.py 中的 COLLECTION_NAME 一致
)


class ChromaDBManager:
    """
    管理 ChromaDB 實例的單例類別。
    確保在應用程式啟動時只載入一次。
    """

    _instance = None

    def __new__(cls):
        """實作單例模式"""
        if cls._instance is None:
            cls._instance = super(ChromaDBManager, cls).__new__(cls)
            cls._instance._db = None
        return cls._instance

    def initialize_db(self):
        """在應用程式啟動時載入 ChromaDB 實例"""
        if self._db is None:
            print(f"[{os.getpid()}] 正在載入或初始化 ChromaDB...")

            # 使用與您的索引建立時相同的嵌入模型
            embeddings = SentenceTransformerEmbeddings(model_name=MODEL_NAME)

            # 檢查 CHROMA_PATH 是否存在並包含數據
            if not os.path.exists(CHROMA_PATH):
                # 如果是 Web Server，理論上索引應該已經存在，這裡應該拋出錯誤或執行初始化邏輯
                raise FileNotFoundError(
                    f"ChromaDB 資料夾未找到於: {CHROMA_PATH}。請先建立索引。"
                )

            # 載入已存在的向量索引
            self._db = Chroma(
                persist_directory=CHROMA_PATH,
                embedding_function=embeddings,
                collection_name=COLLECTION_NAME,  # 指定要從該資料夾中載入的集合
            )
            print(f"[{os.getpid()}] ChromaDB 載入成功！集合名稱: {COLLECTION_NAME}")

    def get_db(self) -> Chroma:
        """提供存取 ChromaDB 實例的接口"""
        if self._db is None:
            raise Exception("ChromaDB 尚未初始化。")
        return self._db


# 實例化管理器
chroma_manager = ChromaDBManager()


# --- 3. 依賴注入 (Dependency Injection) ---


def get_chroma_db() -> Chroma:
    """提供 ChromaDB 實例作為 API 端點的依賴"""
    return chroma_manager.get_db()
