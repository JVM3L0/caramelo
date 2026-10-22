from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from caramelo.adapters.queue.procrastinate import RETRY
from caramelo.adapters.sources.kabum import SourceBlocked


def decide(exception: Exception, attempts: int = 0):
    job = SimpleNamespace(attempts=attempts)
    return RETRY.get_retry_decision(exception=exception, job=job)  # type: ignore[arg-type]


def test_ordinary_failures_are_retried_with_exponential_wait() -> None:
    first, second = decide(RuntimeError(), 0), decide(RuntimeError(), 1)

    assert first is not None and second is not None
    assert first.retry_at is not None and second.retry_at is not None
    now = datetime.now(UTC)
    waits = [(first.retry_at - now).total_seconds(), (second.retry_at - now).total_seconds()]
    assert waits == [pytest.approx(5, abs=1), pytest.approx(25, abs=1)]


def test_gives_up_after_the_last_attempt() -> None:
    assert decide(RuntimeError(), 3) is None


def test_failures_marked_as_not_retryable_are_never_retried() -> None:
    assert decide(SourceBlocked("blocked")) is None
