"""
Webhook Notification Service — dispatches outbound HTTP POST notifications.

FASE 3: Sends event payloads to registered webhook URLs when relevant
events occur in the system (e.g., document analyzed, workflow approved).

Includes HMAC-SHA256 signature for webhook secret verification.
"""
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# Timeout for outbound webhook calls (seconds)
WEBHOOK_TIMEOUT = 10.0


def _compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest for webhook signature verification."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


async def dispatch_webhook(
    url: str,
    event: str,
    data: Dict[str, Any],
    secret: Optional[str] = None,
) -> bool:
    """
    Send a single webhook notification.

    Args:
        url: Target URL to POST to
        event: Event type (e.g., "document.analyzed")
        data: Event payload data
        secret: Optional HMAC secret for signature header

    Returns:
        True if the webhook was delivered successfully (2xx response)
    """
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    payload_bytes = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event,
    }

    if secret:
        signature = _compute_signature(payload_bytes, secret)
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            response = await client.post(url, content=payload_bytes, headers=headers)

        if 200 <= response.status_code < 300:
            logger.info(f"Webhook delivered: {event} → {url} (HTTP {response.status_code})")
            return True
        else:
            logger.warning(
                f"Webhook failed: {event} → {url} (HTTP {response.status_code}): "
                f"{response.text[:200]}"
            )
            return False

    except httpx.TimeoutException:
        logger.error(f"Webhook timeout: {event} → {url}")
        return False
    except Exception as e:
        logger.error(f"Webhook error: {event} → {url}: {e}")
        return False


async def notify_event(
    event: str,
    data: Dict[str, Any],
    db_session=None,
    organization_id=None,
) -> int:
    """
    Look up all active webhooks subscribed to this event and dispatch them.

    Args:
        event: Event type
        data: Event payload
        db_session: Async SQLAlchemy session
        organization_id: Optional filter for org-scoped webhooks

    Returns:
        Number of webhooks successfully delivered
    """
    if not db_session:
        logger.warning(f"notify_event called without db_session for event {event}")
        return 0

    from sqlalchemy import select
    from app import WebhookConfig

    query = select(WebhookConfig).where(
        WebhookConfig.is_active == True,
    )

    # Filter by org or global (null org)
    if organization_id:
        query = query.where(
            (WebhookConfig.organization_id == organization_id) |
            (WebhookConfig.organization_id.is_(None))
        )

    result = await db_session.execute(query)
    webhooks = result.scalars().all()

    delivered = 0
    for wh in webhooks:
        # Check if webhook is subscribed to this event
        if wh.events and event not in wh.events:
            continue

        success = await dispatch_webhook(
            url=wh.url,
            event=event,
            data=data,
            secret=wh.secret,
        )
        if success:
            delivered += 1

    logger.info(f"Event '{event}': {delivered}/{len(webhooks)} webhooks delivered")
    return delivered
