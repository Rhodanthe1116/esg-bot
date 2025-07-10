from fastapi import FastAPI, Request, Header
from langchain_community.chat_models import ChatOpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from dotenv import load_dotenv
import os
import httpx
import json
from langchain import PromptTemplate
from langchain.chains import LLMChain

load_dotenv()

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

# LangChain 設定
initial_prompt = """
你是 AI 永續顧問。當用戶詢問碳足跡相關問題時，請依照以下流程回答：

1. 問用戶提供產品 CCC code 或產品名稱。
2. 收到資訊後，判斷是否有 PCR（Product Category Rules）。
3. 如果有 PCR，提供 PCR 1.2 版的類別說明。
4. 如果無 PCR，請用戶提供中英文名稱、規格與標準等詳細資訊。
5. 持續進行多輪對話直到用戶結束。

請依此流程協助用戶查詢。

用戶訊息：{input}
"""

llm = ChatOpenAI(temperature=0, model="gpt-4")
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
prompt = PromptTemplate(input_variables=["input"], template=initial_prompt)
llm_chain = LLMChain(llm=llm, prompt=prompt)


class CustomConversationChain:
    def __init__(self, llm_chain, memory):
        self.llm_chain = llm_chain
        self.memory = memory

    def predict(self, input: str):
        output = self.llm_chain.run(input=input)
        self.memory.save_context({"input": input}, {"output": output})
        return output


conversation = CustomConversationChain(llm_chain, memory)


# Helper: 回覆 LINE 訊息
async def reply_line(reply_token: str, messages: list):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    data = {"replyToken": reply_token, "messages": messages}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.line.me/v2/bot/message/reply", headers=headers, json=data
        )
        resp.raise_for_status()


@app.post("/webhook")
async def line_webhook(request: Request, x_line_signature: str = Header(None)):
    # 你可以在這裡驗證 x_line_signature 確保安全(此處略過)

    body = await request.json()

    for event in body.get("events", []):
        if event.get("type") == "message" and event["message"].get("type") == "text":
            user_message = event["message"]["text"]
            reply_token = event["replyToken"]

            # LangChain 回覆
            bot_reply = conversation.predict(input=user_message)

            # LINE 回覆訊息格式
            line_messages = [{"type": "text", "text": bot_reply}]

            await reply_line(reply_token, line_messages)

    return "OK"
