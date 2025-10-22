from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
from chroma_manager import chroma_manager, ChromaDBManager
from pcr_router import router as pcr_records_router
from chat_router import router as chat_router
from dotenv import load_dotenv
load_dotenv()

# from line_bot import router as line_bot_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式啟動前 (startup) 和關閉後 (shutdown) 的事件"""
    # 啟動時：載入 ChromaDB
    try:
        chroma_manager.initialize_db()
    except FileNotFoundError as e:
        print(f"嚴重錯誤: {e}")
        # 在實際生產中，您可能需要更優雅的錯誤處理或直接退出

    yield

    # 關閉時：執行清理工作（本地 ChromaDB 通常不需要，但為了標準化保留）
    print(f"[{os.getpid()}] 應用程式關閉，執行清理...")
    pass


# 初始化 FastAPI 應用程式
app = FastAPI(lifespan=lifespan, title="RAG 語義搜尋服務")


# 包含 PCR 記錄的路由
# 所有定義在 pcr_records_router 中的端點都會被加入到主應用程式中
app.include_router(pcr_records_router)
# include AI chat router (front-end uses /api/chat)
app.include_router(chat_router)
# app.include_router(line_bot_router)


# --- 新增靜態檔案服務 ---
# 獲取當前檔案的目錄
current_dir = os.path.dirname(os.path.abspath(__file__))
# 靜態檔案目錄的路徑
static_dir = os.path.join(current_dir, "static")

# 掛載靜態檔案目錄
# 這會讓 FastAPI 從 'static' 目錄提供檔案，並透過 '/static' 路徑訪問
# 例如，如果 index.html 在 static/index.html，則可以透過 http://localhost:8000/static/index.html 訪問
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Configure CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 新增根路徑重定向到前端介面 ---
@app.get(
    "/",
    response_class=HTMLResponse,
    summary="前端介面",
    description="提供環境部PCR記錄查詢的前端網頁介面。",
)
async def serve_frontend():
    """
    當訪問根路徑時，重定向到靜態檔案中的 index.html。
    或者直接返回 index.html 的內容。
    這裡我們直接返回 index.html 的內容，這樣 URL 更簡潔。
    """
    index_html_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_html_path):
        raise HTTPException(
            status_code=404,
            detail="index.html 檔案未找到。請確認它位於 'static' 資料夾中。",
        )
    with open(index_html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
