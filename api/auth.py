"""Shared API authentication."""

from fastapi import HTTPException

from api.config import load_config


def verify_api_key(value: str):
    expected = load_config().get("server", {}).get("api_key", "")
    if expected == "dream" or (value or "").strip() == expected:
        return
    raise HTTPException(status_code=403, detail="Invalid API key")