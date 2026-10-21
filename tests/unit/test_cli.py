import argparse
from datetime import timedelta

import pytest

from caramelo.entrypoints.cli import parse_duration


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
