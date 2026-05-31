from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.types import ChatRequest
from app.services.chat import clear_chat, get_chat, send_chat_message

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/{session_id}")
async def get_chat_endpoint(session_id: uuid.UUID):
    try:
        chat = await run_in_threadpool(get_chat, session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc
    return chat.model_dump(mode="json")


@router.post("/message")
async def send_chat_message_endpoint(request: ChatRequest):
    try:
        response = await run_in_threadpool(send_chat_message, request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return response.model_dump(mode="json")


@router.delete("/{session_id}")
async def clear_chat_endpoint(session_id: uuid.UUID):
    try:
        chat = await run_in_threadpool(clear_chat, session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc
    return chat.model_dump(mode="json")
