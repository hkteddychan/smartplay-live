import pytest
from poller.config import ACTIVITY_EVERY_SECONDS, Settings, SPORTS, ConfigError


def test_sports_order_is_smallest_first():
    assert SPORTS == ["turf-soccer-pitch", "tennis", "basketball", "volleyball", "badminton"]


def test_activity_cadence_is_15_minutes():
    # R51: activity search is not latency-critical (was 300s).
    assert ACTIVITY_EVERY_SECONDS == 900


def test_settings_requires_tg_token(monkeypatch):
    monkeypatch.delenv("TG_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_settings_reads_thread_as_int(monkeypatch):
    monkeypatch.setenv("TG_TOKEN", "x")
    monkeypatch.setenv("TG_CHAT", "5200360037")
    monkeypatch.setenv("TG_THREAD", "68130")
    s = Settings.from_env()
    assert s.tg_thread == 68130 and isinstance(s.tg_thread, int)
