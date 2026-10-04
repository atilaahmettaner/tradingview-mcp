"""Pure-logic tests for scripts/refresh_us_coinlists.py (no network)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "refresh_us_coinlists.py"
_spec = importlib.util.spec_from_file_location("refresh_us_coinlists", _SCRIPT)
refresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refresh)


def test_plan_reports_added_and_removed_per_venue():
    current = {"NASDAQ": {"NASDAQ:AAPL", "NASDAQ:OLD"}, "NYSE": {"NYSE:KO"}}
    live = {"NASDAQ": {"NASDAQ:AAPL", "NASDAQ:NEW"}, "NYSE": {"NYSE:KO"}}

    report = refresh.plan(current, live)

    assert report["venues"]["NASDAQ"] == {"added": ["NASDAQ:NEW"], "removed": ["NASDAQ:OLD"]}
    assert report["venues"]["NYSE"] == {"added": [], "removed": []}
    assert report["moves"] == []


def test_plan_detects_a_cross_venue_move():
    # The #96 case: WMT left NYSE and listed on NASDAQ.
    current = {"NASDAQ": {"NASDAQ:AAPL"}, "NYSE": {"NYSE:KO", "NYSE:WMT"}}
    live = {"NASDAQ": {"NASDAQ:AAPL", "NASDAQ:WMT"}, "NYSE": {"NYSE:KO"}}

    report = refresh.plan(current, live)

    assert report["moves"] == [("WMT", "NYSE", "NASDAQ")]


def test_shrink_guard_blocks_a_suspiciously_small_list():
    current = {"NASDAQ": {f"NASDAQ:S{i}" for i in range(100)}}

    assert refresh.shrink_violations(current, {"NASDAQ": {f"NASDAQ:S{i}" for i in range(40)}}) == ["NASDAQ"]
    assert refresh.shrink_violations(current, {"NASDAQ": {f"NASDAQ:S{i}" for i in range(90)}}) == []


def test_shrink_guard_ignores_a_venue_with_no_current_file():
    assert refresh.shrink_violations({"NASDAQ": set()}, {"NASDAQ": {"NASDAQ:AAPL"}}) == []
