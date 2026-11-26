"""firewalla-exporter: alarm pagination cap and the 429 backoff loop.

The backoff loop exists because 60s retries against a 429-ing MSP API kept the shared
token locked out for ~18h (2026-11-24/25); these tests pin that behaviour.
"""
from unittest.mock import MagicMock

import pytest
import requests

import exporter


class StopLoop(Exception):
    """Raised from a patched time.sleep to break out of the infinite refresh loop."""


def _http_error(status, headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    err = requests.HTTPError(str(status))
    err.response = resp
    return err


def _run_loop(monkeypatch, outcomes, max_sleeps):
    """Drive _refresh_loop with scripted _refresh outcomes; return the sleep durations."""
    sleeps = []
    it = iter(outcomes)

    def fake_refresh():
        out = next(it)
        if isinstance(out, Exception):
            raise out

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= max_sleeps:
            raise StopLoop

    monkeypatch.setattr(exporter, "_refresh", fake_refresh)
    monkeypatch.setattr(exporter.time, "sleep", fake_sleep)
    monkeypatch.setattr(exporter, "POLL_INTERVAL", 300)
    monkeypatch.setattr(exporter, "RATE_LIMIT_WAIT", 660)
    monkeypatch.setattr(exporter, "MAX_BACKOFF", 3600)
    with pytest.raises(StopLoop):
        exporter._refresh_loop()
    return sleeps


def test_success_sleeps_poll_interval(monkeypatch):
    assert _run_loop(monkeypatch, [None, None], 2) == [300, 300]


def test_429_waits_at_least_rate_limit_wait(monkeypatch):
    sleeps = _run_loop(monkeypatch, [_http_error(429)], 1)
    assert sleeps == [660]


def test_429_honours_longer_retry_after(monkeypatch):
    sleeps = _run_loop(monkeypatch, [_http_error(429, {"Retry-After": "1200"})], 1)
    assert sleeps == [1200]


def test_429_ignores_shorter_retry_after(monkeypatch):
    sleeps = _run_loop(monkeypatch, [_http_error(429, {"Retry-After": "30"})], 1)
    assert sleeps == [660]


def test_repeated_429_backs_off_exponentially_and_caps(monkeypatch):
    errs = [_http_error(429)] * 5
    assert _run_loop(monkeypatch, errs, 5) == [660, 1320, 2640, 3600, 3600]


def test_success_resets_backoff(monkeypatch):
    seq = [_http_error(429), _http_error(429), None, _http_error(429)]
    assert _run_loop(monkeypatch, seq, 4) == [660, 1320, 300, 660]


def test_non_429_error_does_not_back_off_and_marks_cache_bad(monkeypatch):
    exporter._cache["ok"] = True
    sleeps = _run_loop(monkeypatch, [_http_error(500)], 1)
    assert sleeps == [300]
    assert exporter._cache["ok"] is False


def test_non_http_exception_does_not_crash_loop(monkeypatch):
    assert _run_loop(monkeypatch, [RuntimeError("boom")], 1) == [300]


def test_alarm_counts_follow_cursor_pagination(monkeypatch):
    pages = iter([
        {"results": [1, 2, 3], "next_cursor": "c1"},
        {"results": [4], "next_cursor": None},
    ])
    calls = []

    def fake_get(path, params=None):
        calls.append(dict(params))
        return next(pages)

    monkeypatch.setattr(exporter, "_get", fake_get)
    assert exporter._fetch_active_alarm_counts([{"gid": "g1"}]) == {"g1": 4}
    assert "cursor" not in calls[0] and calls[1]["cursor"] == "c1"


def test_alarm_pagination_is_hard_capped(monkeypatch):
    n = {"calls": 0}

    def endless(path, params=None):
        n["calls"] += 1
        return {"results": [1], "next_cursor": "again"}

    monkeypatch.setattr(exporter, "_get", endless)
    assert exporter._fetch_active_alarm_counts([{"gid": "g1"}]) == {"g1": 20}
    assert n["calls"] == 20
