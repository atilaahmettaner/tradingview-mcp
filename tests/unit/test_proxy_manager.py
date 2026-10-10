import urllib.parse

import pytest

from tradingview_mcp.core.services import proxy_manager

PROXY_VARS = (
    "PROXY_PROVIDER", "PROXY_HOST", "PROXY_PORT", "PROXY_USERNAME_PREFIX",
    "PROXY_USERNAME_TEMPLATE", "PROXY_PASSWORD", "PROXY_ENABLED",
    "PROXY_SESSION_MIN", "PROXY_SESSION_MAX",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PROXY_PASSWORD", "pw")
    # A single-value range makes the session id predictable.
    monkeypatch.setenv("PROXY_SESSION_MIN", "7")
    monkeypatch.setenv("PROXY_SESSION_MAX", "7")


def parts(url):
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.unquote(parsed.username), parsed.hostname, parsed.port


def test_default_is_webshare(monkeypatch):
    monkeypatch.setenv("PROXY_USERNAME_PREFIX", "abcd")
    assert parts(proxy_manager.get_proxy_url()) == ("abcd-7", "p.webshare.io", 80)


def test_nodemaven_preset(monkeypatch):
    monkeypatch.setenv("PROXY_PROVIDER", "NodeMaven")
    monkeypatch.setenv("PROXY_USERNAME_PREFIX", "login-country-us")
    assert parts(proxy_manager.get_proxy_url()) == (
        "login-country-us-sid-7", "gate.nodemaven.com", 8080)


def test_host_and_port_override_the_preset(monkeypatch):
    monkeypatch.setenv("PROXY_PROVIDER", "nodemaven")
    monkeypatch.setenv("PROXY_USERNAME_PREFIX", "login")
    monkeypatch.setenv("PROXY_HOST", "127.0.0.1")
    monkeypatch.setenv("PROXY_PORT", "3128")
    assert parts(proxy_manager.get_proxy_url()) == ("login-sid-7", "127.0.0.1", 3128)


def test_custom_template(monkeypatch):
    monkeypatch.setenv("PROXY_USERNAME_PREFIX", "user")
    monkeypatch.setenv("PROXY_USERNAME_TEMPLATE", "{prefix}-session-{session}-ttl-10m")
    assert parts(proxy_manager.get_proxy_url())[0] == "user-session-7-ttl-10m"


@pytest.mark.parametrize("template", ["{prefix}-fixed", "user-{session}", "plain"])
def test_template_missing_a_placeholder_falls_back(monkeypatch, capsys, template):
    monkeypatch.setenv("PROXY_USERNAME_PREFIX", "abcd")
    monkeypatch.setenv("PROXY_USERNAME_TEMPLATE", template)
    assert parts(proxy_manager.get_proxy_url())[0] == "abcd-7"
    assert "PROXY_USERNAME_TEMPLATE" in capsys.readouterr().err


def test_unknown_provider_falls_back_to_webshare(monkeypatch, capsys):
    monkeypatch.setenv("PROXY_PROVIDER", "nope")
    monkeypatch.setenv("PROXY_USERNAME_PREFIX", "abcd")
    assert parts(proxy_manager.get_proxy_url()) == ("abcd-7", "p.webshare.io", 80)
    assert "PROXY_PROVIDER" in capsys.readouterr().err


def test_braces_in_the_prefix_are_kept(monkeypatch):
    monkeypatch.setenv("PROXY_USERNAME_PREFIX", "a{b}c")
    assert parts(proxy_manager.get_proxy_url())[0] == "a{b}c-7"


def test_opener_authenticates_with_the_templated_username(monkeypatch):
    monkeypatch.setenv("PROXY_PROVIDER", "nodemaven")
    monkeypatch.setenv("PROXY_USERNAME_PREFIX", "login")
    opener = proxy_manager.build_opener_with_proxy()
    handler = next(h for h in opener.handlers
                   if h.__class__.__name__ == "ProxyBasicAuthHandler")
    user, password = handler.passwd.find_user_password(None, "http://gate.nodemaven.com:8080")
    assert (user, password) == ("login-sid-7", "pw")
