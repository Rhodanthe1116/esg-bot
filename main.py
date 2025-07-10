
from fastapi import FastAPI, Request
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

llm = ChatOpenAI(temperature=0, model="gpt-4")
memory = ConversationBufferMemory()
conversation = ConversationChain(
    llm=llm,
    memory=memory,
    verbose=True
)

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    user_message = data.get('events', [{}])[0].get('message', {}).get('text', '')

    reply = conversation.predict(input=user_message)

    print(f"\n👤 User: {user_message}")
    print(f"🤖 Bot: {reply}\n")

    return {"reply": reply}
