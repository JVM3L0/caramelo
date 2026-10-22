"""Procrastinate-backed job queue (jobs stored in Postgres).

This is the only module that imports procrastinate. Swapping the queue (e.g. for
Redis + arq) means writing another module with the same functions and class.
"""

from collections.abc import Mapping
from typing import Any

import procrastinate
from procrastinate.jobs import Job
from procrastinate.retry import RetryDecision

from caramelo.application.jobs import JobHandler
from caramelo.application.ports import JobPayload


class _Retry(procrastinate.RetryStrategy):
    """3 attempts in total, waiting 5s then 10s, except for failures that say retrying
    is pointless (`retryable = False`), such as a block by the store."""

    def get_retry_decision(self, *, exception: BaseException, job: Job) -> RetryDecision | None:
        if getattr(exception, "retryable", True) is False:
            return None
        return super().get_retry_decision(exception=exception, job=job)


RETRY = _Retry(max_attempts=3, exponential_wait=5)


def create_app(conninfo: str) -> procrastinate.App:
    return procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=conninfo))


def register(
    app: procrastinate.App,
    handlers: Mapping[str, JobHandler],
    periodic: Mapping[str, str] | None = None,
) -> None:
    """Registers each handler as a task; `periodic` maps handler names to cron expressions."""
    periodic = periodic or {}
    for name, handler in handlers.items():
        if name in periodic:
            _register_periodic(app, name, handler, periodic[name])
        else:
            app.task(name=name, retry=RETRY)(handler)


def _register_periodic(app: procrastinate.App, name: str, handler: JobHandler, cron: str) -> None:
    # Procrastinate passes the scheduled timestamp; our handlers don't need it.
    async def run(timestamp: int) -> None:
        await handler()

    # No retries: the next tick runs it again anyway. The lock keeps ticks from overlapping.
    app.periodic(cron=cron, periodic_id=name)(app.task(name=name, lock=name)(run))


async def ensure_schema(app: procrastinate.App) -> None:
    """Applies procrastinate's own tables once; safe to run on every deploy."""
    row = await app.connector.execute_query_one_async(
        "SELECT to_regclass('procrastinate_jobs') IS NOT NULL AS present"
    )
    if not row["present"]:
        await app.schema_manager.apply_schema_async()


async def run_worker(app: procrastinate.App) -> None:
    await app.run_worker_async()


class ProcrastinateTaskQueue:
    def __init__(self, app: procrastinate.App) -> None:
        self._app = app

    async def enqueue(self, job: str, *, lock: str | None = None, **payload: JobPayload) -> None:
        kwargs: dict[str, Any] = dict(payload)
        await self._app.configure_task(job, lock=lock).defer_async(**kwargs)
