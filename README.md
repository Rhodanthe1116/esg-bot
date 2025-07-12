
# Sustainability Consultant AI Bot

✅ FastAPI + LangChain + GPT-4  
💡 專為碳盤查與永續顧問對話設計的快速原型。

---

## 🚀 使用方式

```bash
git clone <repo>
cd sustainability-consultant-bot
pip install -r requirements.txt

# 複製環境變數
cp .env.example .env
# 並填入你的 OPENAI KEY

# 執行
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 🚀 測試

```bash
curl -X POST http://127.0.0.1:8000/webhook \
 -H "Content-Type: application/json" \
 -d '{"events": [{"message": {"text": "我要查碳足跡"}}]}'
```
