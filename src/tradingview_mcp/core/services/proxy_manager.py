"""
Proxy Manager Service for tradingview-mcp.

Reads proxy credentials from ENVIRONMENT VARIABLES only.
Never hardcode credentials in this file.

Setup (Webshare, the default):
    export PROXY_HOST=p.webshare.io
    export PROXY_PORT=80
    export PROXY_USERNAME_PREFIX=hvfvdamo   # your username prefix
    export PROXY_PASSWORD=your_password_here

Other residential gateways put the sticky session id somewhere else in the
username. PROXY_PROVIDER picks a preset for host, port and username format:

    export PROXY_PROVIDER=nodemaven
    export PROXY_USERNAME_PREFIX=your_login-country-us   # targeting goes here
    export PROXY_PASSWORD=your_password_here

PROXY_HOST and PROXY_PORT still override the preset, and
PROXY_USERNAME_TEMPLATE (with {prefix} and {session}) covers any other gateway.

Or create a .env file (see .env.example) — never commit .env to git.

Usage:
    from tradingview_mcp.core.services.proxy_manager import get_proxy, build_opener_with_proxy

    proxies = get_proxy()                    # for requests library
    opener  = build_opener_with_proxy()      # for urllib
"""
from __future__ import annotations

import os
import random
import urllib.parse
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

def _env_int(name: str, default: int) -> int:
    """Read an int env var; a malformed value falls back with a stderr note
    instead of raising ValueError out of every proxied request."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        import sys
        print(f"[tradingview_mcp] ignoring non-numeric {name}={raw!r}, "
              f"using {default}", file=sys.stderr)
        return default


# Host, port and username format per gateway. {session} is the sticky session
# id: the same id keeps the same exit IP, a new id gets a new one.
PROVIDERS: dict[str, dict[str, str]] = {
    "webshare": {"host": "p.webshare.io", "port": "80",
                 "template": "{prefix}-{session}"},
    "nodemaven": {"host": "gate.nodemaven.com", "port": "8080",
                  "template": "{prefix}-sid-{session}"},
}
DEFAULT_PROVIDER = "webshare"


def _note(message: str) -> None:
    import sys
    print(f"[tradingview_mcp] {message}", file=sys.stderr)


def _provider() -> dict[str, str]:
    name = os.environ.get("PROXY_PROVIDER", "").strip().lower() or DEFAULT_PROVIDER
    if name not in PROVIDERS:
        _note(f"unknown PROXY_PROVIDER={name!r}, using {DEFAULT_PROVIDER!r} "
              f"(known: {', '.join(sorted(PROVIDERS))})")
        name = DEFAULT_PROVIDER
    return PROVIDERS[name]


def _username_template(default: str) -> str:
    """PROXY_USERNAME_TEMPLATE, or the preset's. A template without both
    placeholders would drop the login or pin every request to one exit, so it
    falls back with a stderr note instead."""
    template = os.environ.get("PROXY_USERNAME_TEMPLATE", "")
    if not template:
        return default
    if "{prefix}" not in template or "{session}" not in template:
        _note(f"ignoring PROXY_USERNAME_TEMPLATE={template!r}: it needs both "
              f"{{prefix}} and {{session}}, using {default!r}")
        return default
    return template


def _cfg() -> dict:
    preset = _provider()
    return {
        "host":    os.environ.get("PROXY_HOST", preset["host"]),
        "port":    os.environ.get("PROXY_PORT", preset["port"]),
        "template": _username_template(preset["template"]),
        "prefix":  os.environ.get("PROXY_USERNAME_PREFIX", ""),
        "password": os.environ.get("PROXY_PASSWORD", ""),
        "enabled": os.environ.get("PROXY_ENABLED", "true").lower() == "true",
        "min":     _env_int("PROXY_SESSION_MIN", 1),
        "max":     _env_int("PROXY_SESSION_MAX", 250),
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
    # URL-encode credentials: a password containing @ : / or # would
    # otherwise produce a proxy URL that parses to the wrong host/auth.
    username = c["template"].replace("{prefix}", c["prefix"]).replace(
        "{session}", str(session_id))
    user = urllib.parse.quote(username, safe="")
    pwd = urllib.parse.quote(c["password"], safe="")
    return f"http://{user}:{pwd}@{c['host']}:{c['port']}"


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
    # Extract username from the full url for auth handler (unquote — the URL
    # form is percent-encoded; the password manager wants the raw value).
    username = urllib.parse.unquote(proxy_url.split("//")[1].split(":")[0])

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
