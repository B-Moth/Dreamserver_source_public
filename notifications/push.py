"""
push.py — Web Push notification module for Sandman
- Manages push subscriptions from the PWA
- Sends notifications when transcription is complete
- Uses VAPID keys for authentication
- Stores subscriptions in a local JSON file
"""

import json
import logging
from pathlib import Path

import yaml
from pywebpush import webpush, WebPushException

# ── Logging ────────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / "dreamserver" / "config.yaml"
SUBS_FILE = Path.home() / "dreamserver" / "subscriptions.json"


def _load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def _load_subscriptions() -> list:
    if not SUBS_FILE.exists():
        return []
    with open(SUBS_FILE) as f:
        return json.load(f)


def _save_subscriptions(subs: list):
    SUBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SUBS_FILE, "w") as f:
        json.dump(subs, f, indent=2)


# ── Public API ─────────────────────────────────────────────────────────────────


def add_subscription(subscription: dict):
    """
    Register a new push subscription from the PWA.
    subscription is the PushSubscription object from the browser.
    """
    subs = _load_subscriptions()

    # Avoid duplicates — replace if endpoint already exists
    endpoint = subscription.get("endpoint")
    subs = [s for s in subs if s.get("endpoint") != endpoint]
    subs.append(subscription)

    _save_subscriptions(subs)
    log.info(f"Push subscription registered (total: {len(subs)})")


def remove_subscription(endpoint: str):
    """Remove a subscription by endpoint URL."""
    subs = _load_subscriptions()
    subs = [s for s in subs if s.get("endpoint") != endpoint]
    _save_subscriptions(subs)
    log.info(f"Push subscription removed (total: {len(subs)})")


def send_notification(title: str, body: str, data: dict = None):
    """
    Send a push notification to all registered subscribers.

    title: notification title
    body:  notification body text
    data:  optional dict with extra data (e.g. entry timestamp for deep link)
    """
    config = _load_config()
    push_cfg = config.get("push", {})
    vapid_key = push_cfg.get("vapid_private_key", "") or push_cfg.get(
        "vapid_private_key_file", ""
    )
    vapid_email = push_cfg.get("vapid_email", "")

    if not vapid_key or not vapid_email:
        log.warning("Push notifications not configured — skipping")
        return

    subs = _load_subscriptions()
    if not subs:
        log.info("No push subscribers — skipping notification")
        return

    payload = json.dumps(
        {"notification": {"title": title, "body": body, "data": data or {}}}
    )

    failed = []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=vapid_key,
                vapid_claims={"sub": f"mailto:{vapid_email}"},
                headers={"Content-Type": "application/json"},
            )
            log.info(f"Push sent to {sub.get('endpoint', '')[:50]}...")
        except WebPushException as e:
            log.error(f"Push failed: {e}")
            # If subscription is gone (410) remove it
            if e.response and e.response.status_code in (404, 410):
                log.info("Removing expired subscription")
                failed.append(sub.get("endpoint"))
        except Exception as e:
            log.error(f"Push error: {e}")

    # Clean up expired subscriptions
    if failed:
        subs = [s for s in subs if s.get("endpoint") not in failed]
        _save_subscriptions(subs)


def send_transcript_ready(timestamp: str, transcript_preview: str, fuzzy: bool = False):
    """
    Convenience function — send notification when a transcript is ready.
    transcript_preview: first ~100 chars of the transcript
    """
    title = "🌙 Nouveau rêve transcrit"
    if fuzzy:
        title = "🌙 Nouveau rêve transcrit ⚠"

    # Trim preview to 100 chars
    preview = transcript_preview[:100]
    if len(transcript_preview) > 100:
        preview += "..."

    send_notification(
        title=title,
        body=preview,
        data={"timestamp": timestamp, "url": f"/entries/{timestamp}"},
    )


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Test: send a test notification to all subscribers.
    Usage: python3 push.py
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [push] %(message)s")

    subs = _load_subscriptions()
    print(f"Registered subscribers: {len(subs)}")

    if subs:
        send_notification(
            title="DreamCatcher test",
            body="Push notifications are working!",
            data={"test": True},
        )
    else:
        print("No subscribers yet — install the PWA first to register.")
