"""
Proxy Manager Service for tradingview-mcp.

Reads Webshare proxy credentials from ENVIRONMENT VARIABLES only.
Never hardcode credentials in this file.

Setup:
    export PROXY_HOST=p.webshare.io
    export PROXY_PORT=80
    export PROXY_USERNAME_PREFIX=hvfvdamo   # your username prefix
    export PROXY_PASSWORD=your_password_here

Or create a .env file (see .env.example) — never commit .env to git.

Usage:
    from tradingview_mcp.core.services.proxy_manager import get_proxy, build_opener_with_proxy

    proxies = get_proxy()                    # for requests library
    opener  = build_opener_with_proxy()      # for urllib
"""
from __future__ import annotations

import os
import random
import urllib.request
from typing import Optional

# Try loading .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "../../../../.env")
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass


# ─── Read config from env ─────────────────────────────────────────────────────

def _cfg() -> dict:
    return {
        "host":    os.environ.get("PROXY_HOST", "p.webshare.io"),
        "port":    os.environ.get("PROXY_PORT", "80"),
        "prefix":  os.environ.get("PROXY_USERNAME_PREFIX", ""),
        "password": os.environ.get("PROXY_PASSWORD", ""),
        "enabled": os.environ.get("PROXY_ENABLED", "true").lower() == "true",
        "min":     int(os.environ.get("PROXY_SESSION_MIN", "1")),
        "max":     int(os.environ.get("PROXY_SESSION_MAX", "250")),
    }


def is_proxy_configured() -> bool:
    """Returns True only if all required env vars are set."""
    c = _cfg()
    return c["enabled"] and bool(c["prefix"]) and bool(c["password"])


def get_proxy_url() -> Optional[str]:
    """Build a rotating proxy URL with a random sticky session. Returns None if not configured."""
    if not is_proxy_configured():
        return None
    c = _cfg()
    session_id = random.randint(c["min"], c["max"])
    return f"http://{c['prefix']}-{session_id}:{c['password']}@{c['host']}:{c['port']}"


def get_proxy() -> Optional[dict]:
    """Return proxy dict for the `requests` library. Returns None if not configured."""
    url = get_proxy_url()
    if not url:
        return None
    return {"http": url, "https": url}


def get_httpx_proxy() -> Optional[str]:
    """Return a single proxy URL string for ``httpx.AsyncClient(proxy=...)``.

    Returns None if not configured. httpx (0.27+) accepts a single ``proxy``
    arg that applies to both http and https, which matches how this repo
    has always treated the Webshare proxy.
    """
    return get_proxy_url()


def build_opener_with_proxy(
    user_agent: str = "tradingview-mcp/0.5.0",
) -> urllib.request.OpenerDirector:
    """
    Build a urllib OpenerDirector with proxy if configured, plain opener otherwise.
    Services degrade gracefully when no proxy is set — no crashes.
    """
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", user_agent)]

    if not is_proxy_configured():
        return opener

    proxy_url = get_proxy_url()
    c = _cfg()
    # Extract username from the full url for auth handler
    username = proxy_url.split("//")[1].split(":")[0]

    proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    pwd_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    pwd_mgr.add_password(None, f"http://{c['host']}:{c['port']}", username, c["password"])
    auth_handler = urllib.request.ProxyBasicAuthHandler(pwd_mgr)

    opener = urllib.request.build_opener(proxy_handler, auth_handler)
    opener.addheaders = [("User-Agent", user_agent)]
    return opener


def check_proxy() -> dict:
    """Test proxy connectivity. Returns current exit IP, country, city."""
    import json

    status: dict = {
        "configured": is_proxy_configured(),
        "ok": False,
        "ip": None, "country": None, "city": None, "error": None,
    }

    if not is_proxy_configured():
        status["error"] = (
            "Proxy not configured. Set PROXY_HOST, PROXY_USERNAME_PREFIX, "
            "PROXY_PASSWORD in your environment or .env file."
        )
        return status

    try:
        proxy_url = get_proxy_url()
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener  = urllib.request.build_opener(handler)
        opener.addheaders = [("User-Agent", "tradingview-mcp/0.5.0")]
        req = urllib.request.Request("https://ipinfo.io/json")
        with opener.open(req, timeout=12) as resp:
            data = json.loads(resp.read())
        status.update(ip=data.get("ip"), country=data.get("country"),
                      city=data.get("city"), ok=True)
    except Exception as e:
        status["error"] = str(e)

    return status
