from fastapi import FastAPI

from app.router import route
from app.schemas import ChatRequest, ChatResponse

app = FastAPI(title="gate.atla.in")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    return await route(req)
