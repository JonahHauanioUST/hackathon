"""
Database layer, Pydantic models, and LLM helper.
"""

import json
import os
import sqlite3
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).parent / "chat.db"

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = """You are generating a summary of changes in a series of merge requests. The merge requests are provided as a list of URLs. Each URL is a link to a Gitlab Merge Request. Please read through the changes and provide a detailed but concise summary of all changes."""


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    urls: list[str] = Field(default_factory=list, description="List of URLs")


class ChatResponse(BaseModel):
    id: str
    message: str
    urls: list[str]
    llm_reply: str | None
    created_at: str


# ── DB helpers ────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id          TEXT PRIMARY KEY,
                message     TEXT NOT NULL,
                urls        TEXT NOT NULL,
                llm_reply   TEXT,
                created_at  TEXT NOT NULL
            )
        """)


def insert_chat(chat_id, message, urls, llm_reply, created_at):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO chats (id, message, urls, llm_reply, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, message, json.dumps(urls), llm_reply, created_at),
        )


def fetch_chat(chat_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()


def fetch_recent_chats(limit=50):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM chats ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


# ── LLM call ─────────────────────────────────────────────────

def _build_user_content(message: str, urls: list[str]) -> str:
    if not urls:
        return message
    url_block = "\n".join(f"- {u}" for u in urls)
    return f"{message}\n\nReferenced URLs:\n{url_block}"


async def query_llm(message: str, urls: list[str]) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post (
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": _build_user_content(message, urls)}
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]