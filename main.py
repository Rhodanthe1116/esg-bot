from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
from pcr_router import router as pcr_records_router
from line_bot import router as line_bot_router

app = FastAPI()


# 包含 PCR 記錄的路由
# 所有定義在 pcr_records_router 中的端點都會被加入到主應用程式中
app.include_router(pcr_records_router)
app.include_router(line_bot_router)



# --- 新增靜態檔案服務 ---
# 獲取當前檔案的目錄
current_dir = os.path.dirname(os.path.abspath(__file__))
# 靜態檔案目錄的路徑
static_dir = os.path.join(current_dir, "static")

# 掛載靜態檔案目錄
# 這會讓 FastAPI 從 'static' 目錄提供檔案，並透過 '/static' 路徑訪問
# 例如，如果 index.html 在 static/index.html，則可以透過 http://localhost:8000/static/index.html 訪問
app.mount("/static", StaticFiles(directory=static_dir), name="static")


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
