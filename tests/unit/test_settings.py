from datetime import timedelta

import pytest

from caramelo.entrypoints.settings import Settings


def settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(f"CARAMELO_{key.upper()}", value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_defaults_are_gentle(monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(monkeypatch)

    assert config.default_collect_interval == timedelta(hours=1)
    assert config.seed_collect_interval == timedelta(hours=2)
    assert config.source_block_cooldown == timedelta(minutes=30)
    assert config.request_min_interval == 2.0
    assert config.http_proxy is None


def test_durations_accept_the_short_format(monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(
        monkeypatch,
        default_collect_interval="30m",
        seed_collect_interval="3h",
        source_block_cooldown="1h30m",
    )

    assert config.default_collect_interval == timedelta(minutes=30)
    assert config.seed_collect_interval == timedelta(hours=3)
    assert config.source_block_cooldown == timedelta(minutes=90)


def test_durations_still_accept_iso_8601(monkeypatch: pytest.MonkeyPatch) -> None:
    config = settings(monkeypatch, seed_collect_interval="PT10M")

    assert config.seed_collect_interval == timedelta(minutes=10)


def test_garbage_duration_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    for bad in ("5x", "600", "two hours"):
        with pytest.raises(ValueError, match="invalid duration"):
            settings(monkeypatch, seed_collect_interval=bad)
