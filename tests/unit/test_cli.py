import argparse
from datetime import timedelta

import pytest

from caramelo.entrypoints.cli import describe_seed, parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [("30m", timedelta(minutes=30)), ("2h", timedelta(hours=2)), ("1h30m", timedelta(minutes=90))],
)
def test_parse_duration(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "30", "abc", "1x", "5m!"])
def test_parse_duration_rejects_garbage(text: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_duration(text)


def test_describe_seed_states_the_cost_before_anything_is_sent() -> None:
    text = describe_seed("hardware/ssd", pages=2, every=timedelta(hours=2), request_min_interval=2)

    assert "até 2 requisição(ões)" in text
    assert "até 120 produtos" in text
    assert "~60 requisições/hora" in text  # 120 products every 2 h
