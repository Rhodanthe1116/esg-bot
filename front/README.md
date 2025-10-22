# esgAI 顧問 — front

這是前端 React 應用程式，簡單模擬類似 Gemini 的 AI 對話介面，標題為 `esgAI顧問`。

快速開始

1. 進入 `front` 目錄
2. 安裝依賴：`npm install` 或 `pnpm install`
3. 啟動開發伺服器：`npm run dev`


注意：前端在運行時會向 env 變數 `VITE_API_BASE` 指定的主機發出 API 請求（例如 `VITE_API_BASE=http://localhost:8000`）。若未設定，前端會向相同 origin 的 `/api` 發出請求。

啟動後端（範例）

```bash
# 在專案根目錄啟動 FastAPI
uvicorn main:app --reload
```

設定 API Base

1. 在 `front` 目錄複製 `.env.example` 成 `.env`，或在啟動前導出環境變數：

```bash
# 於 front 資料夾
cp .env.example .env
# 或在 Windows bash 中
export VITE_API_BASE=http://localhost:8000
```

2. 啟動前端：

```bash
npm run dev
```

後端路由

前端會向 `${VITE_API_BASE}/api/chat` 送出 POST，後端應提供 `/api/chat` 並回傳 `{ reply: string }`。

建議

- 如果要把前端與現有 Python 後端整合，可在後端新增 `/api/chat` 路由，接收 `messages` 陣列並回傳 `{ reply: string }`。
