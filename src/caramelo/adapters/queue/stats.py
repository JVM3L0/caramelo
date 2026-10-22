"""Queue statistics for the dashboard, read from procrastinate's own tables."""

import procrastinate

from caramelo.application.dashboard import QueueStats


class ProcrastinateQueueStatistics:
    def __init__(self, app: procrastinate.App) -> None:
        self._app = app

    async def stats(self) -> QueueStats:
        rows = await self._app.connector.execute_query_all_async(
            "SELECT status::text AS status, count(*) AS n FROM procrastinate_jobs GROUP BY status"
        )
        counts = {row["status"]: row["n"] for row in rows}
        oldest = await self._app.connector.execute_query_one_async(
            # scheduled_at is only set for jobs deferred into the future; for the others, the
            # moment they entered the queue is their 'deferred' event.
            "SELECT min(COALESCE(j.scheduled_at, e.at)) AS at FROM procrastinate_jobs j "
            "LEFT JOIN procrastinate_events e ON e.job_id = j.id AND e.type = 'deferred' "
            "WHERE j.status = 'todo'"
        )
        return QueueStats(
            pending=counts.get("todo", 0),
            running=counts.get("doing", 0),
            failed=counts.get("failed", 0),
            oldest_pending_at=oldest["at"],
        )
