"""
FastAPI routes for the Chat API.
"""

import uuid
import json
import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db import (
    ChatRequest, ChatResponse,
    init_db, insert_chat, fetch_chat, fetch_recent_chats, query_llm,
)


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="Chat API", version="0.1.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    chat_id = str(uuid.uuid4())
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        llm_reply = await query_llm(req.message, req.urls)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    try:
        insert_chat(chat_id, req.message, req.urls, llm_reply, created_at)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    return ChatResponse(
        id=chat_id,
        message=req.message,
        urls=req.urls,
        llm_reply=llm_reply,
        created_at=created_at,
    )


@app.get("/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(chat_id: str):
    row = fetch_chat(chat_id)
    if not row:
        raise HTTPException(status_code=404, detail="Chat not found")
    return ChatResponse(
        id=row["id"],
        message=row["message"],
        urls=json.loads(row["urls"]),
        llm_reply=row["llm_reply"],
        created_at=row["created_at"],
    )


@app.get("/chats", response_model=list[ChatResponse])
async def list_chats(limit: int = 50):
    rows = fetch_recent_chats(limit)
    return [
        ChatResponse(
            id=r["id"],
            message=r["message"],
            urls=json.loads(r["urls"]),
            llm_reply=r["llm_reply"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

