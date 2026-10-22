import argparse
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from caramelo.entrypoints.cli import configure_logging, describe_seed, parse_duration


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


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def test_the_dashboard_never_logs_to_the_terminal(restore_logging, tmp_path: Path) -> None:
    log_file = tmp_path / "state" / "dashboard.log"

    configure_logging("dashboard", log_file)

    streams = [h for h in restore_logging.handlers if type(h) is logging.StreamHandler]
    assert streams == []  # a StreamHandler would write over the screen
    logging.getLogger("procrastinate").info("Adding tasks from blueprint")
    logging.getLogger("caramelo").warning("database unreachable")
    for handler in restore_logging.handlers:
        handler.flush()
    text = log_file.read_text()
    assert "database unreachable" in text
    assert "Adding tasks from blueprint" not in text  # info is not worth a file


def test_other_commands_log_to_the_terminal(restore_logging) -> None:
    configure_logging("worker")

    assert restore_logging.level == logging.INFO
    assert any(type(h) is logging.StreamHandler for h in restore_logging.handlers)
