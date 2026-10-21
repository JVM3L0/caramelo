"""Procrastinate-backed job queue (jobs stored in Postgres).

This is the only module that imports procrastinate. Swapping the queue (e.g. for
Redis + arq) means writing another module with the same three functions/classes.
"""

from collections.abc import Mapping

import procrastinate

from caramelo.application.jobs import JobHandler
from caramelo.application.ports import JobPayload


def build_app(conninfo: str, handlers: Mapping[str, JobHandler]) -> procrastinate.App:
    app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=conninfo))
    for name, handler in handlers.items():
        app.task(name=name, retry=3)(handler)
    return app


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

    async def enqueue(self, job: str, **payload: JobPayload) -> None:
        await self._app.configure_task(job).defer_async(**payload)
