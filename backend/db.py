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

SUMMARY_SYSTEM_PROMPT = """You are generating a summary of changes in a series of merge requests. The merge requests are provided as a list of URLs. Each URL is a link to a Gitlab Merge Request. Please read through the changes and provide a detailed but concise summary of all changes."""

CHANGE_REQUEST_SYSTEM_PROMPT = """You are generating a formal Change Request document. You will be given a summary of code changes and optionally a text description providing additional context.

Produce a structured Change Request with the following sections:

## Summary of Changes
A clear, concise summary of what is being changed and why.

## Business Justification
Why this change is needed from a business perspective. Tie technical changes back to business value, risk reduction, or compliance needs.

## Deployment Timeline
A realistic timeline for deploying these changes, including any pre-deployment steps, the deployment window, and post-deployment verification.

## Rollback Plan
A detailed plan for reverting the changes if something goes wrong, including specific steps, estimated rollback time, and criteria for triggering a rollback.

Be professional and thorough. Use the provided description for additional context about the motivation and constraints."""


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    urls: list[str] = Field(default_factory=list, description="List of URLs")


class ChangeRequestRequest(BaseModel):
    description: str = Field(default="", description="Additional context for the change request")
    urls: list[str] = Field(default_factory=list, description="List of URLs to summarize")


class ChangeRequestResponse(BaseModel):
    id: str
    description: str
    urls: list[str]
    summary: str
    change_request: str
    created_at: str


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
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1024,
                "system": SUMMARY_SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": _build_user_content(message, urls)}
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def generate_change_request(summary: str, description: str) -> str:
    user_content = f"## Change Summary\n{summary}"
    if description.strip():
        user_content += f"\n\n## Additional Context\n{description}"
    user_content += "\n\nPlease generate a formal Change Request document."

    async with httpx.AsyncClient(timeout=90, verify=False) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 2048,
                "system": CHANGE_REQUEST_SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": user_content}
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]