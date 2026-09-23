"""Vocabulary, profile, and Web Push routes."""

from pathlib import Path
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from api.auth import verify_api_key
from api.config import load_config
from api.profile import load_user_profile, sanitize_user_profile, save_user_profile
from notifications.push import add_subscription, remove_subscription

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/vocabulary")
def get_vocabulary(x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    path = Path(load_config().get("vocabulary_file", ""))
    return JSONResponse({"vocabulary": path.read_text() if path.exists() else ""})


@router.post("/vocabulary/update")
async def update_vocabulary(request: Request, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    path = Path(load_config().get("vocabulary_file", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    vocabulary = (await request.json()).get("vocabulary", "")
    path.write_text(vocabulary)
    log.info(f"Vocabulary updated: {vocabulary[:50]}...")
    return JSONResponse({"status": "ok"})


@router.post("/vocabulary/add")
async def add_vocabulary_word(request: Request, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    path = Path(load_config().get("vocabulary_file", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    word = (await request.json()).get("word", "").strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word is required")
    existing = path.read_text().strip() if path.exists() else ""
    words = [item.strip() for item in existing.split(",") if item.strip()]
    if word in words:
        return JSONResponse({"status": "ok", "added": False, "message": "Already in vocabulary"})
    words.append(word)
    path.write_text(", ".join(words))
    log.info(f"Vocabulary word added: {word}")
    return JSONResponse({"status": "ok", "added": True})


@router.get("/profile")
def get_profile(x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    return JSONResponse(load_user_profile())


@router.post("/profile/update")
async def update_profile(request: Request, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    body = await request.json()
    profile = sanitize_user_profile(body if isinstance(body, dict) else {})
    save_user_profile(profile)
    return JSONResponse({"status": "ok", "profile": profile})


@router.post("/push/subscribe")
async def push_subscribe(request: Request, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    add_subscription(await request.json())
    return JSONResponse({"status": "ok"})


@router.delete("/push/subscribe")
async def push_unsubscribe(request: Request, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    endpoint = (await request.json()).get("endpoint")
    if endpoint:
        remove_subscription(endpoint)
    return JSONResponse({"status": "ok"})


@router.get("/push/key")
def push_public_key(x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    return JSONResponse({"public_key": load_config().get("push", {}).get("vapid_public_key", "")})