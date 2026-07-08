"""FXMacroData release-calendar service helpers."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

FXMACRODATA_BASE_URL = "https://fxmacrodata.com/api/v1"


async def get_release_calendar(
    currency: str = "usd",
    *,
    limit: int = 25,
    min_tier: Optional[int] = None,
    base_url: str = FXMACRODATA_BASE_URL,
) -> dict[str, Any]:
    """Fetch FXMacroData official-source release-calendar events."""

    limit_count = max(1, min(int(limit), 100))
    params: dict[str, str] = {"limit": str(limit_count)}
    api_key = os.getenv("FXMACRODATA_API_KEY")
    if api_key:
        params["api_key"] = api_key

    url = f"{base_url.rstrip('/')}/calendar/{currency.lower()}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()

    events = payload.get("data", [])
    if min_tier is not None:
        events = [
            event
            for event in events
            if int(event.get("market_tier") or 99) <= min_tier
        ]

    events = events[:limit_count]
    return {
        "currency": payload.get("currency", currency.upper()),
        "timezone": payload.get("timezone"),
        "data_quality": payload.get("data_quality"),
        "events": events,
    }
