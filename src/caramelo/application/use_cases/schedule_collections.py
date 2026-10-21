from collections import defaultdict
from collections.abc import Callable

from caramelo.application import jobs
from caramelo.application.ports import Clock, TaskQueue, UnitOfWork


class ScheduleDueCollections:
    """Turns due monitored listings into collection jobs, batched per store."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        queue: TaskQueue,
        clock: Clock,
        batch_size: int = 20,
        max_claim: int = 500,
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue
        self._clock = clock
        self._batch_size = batch_size
        self._max_claim = max_claim

    async def __call__(self) -> int:
        async with self._uow_factory() as uow:
            due = await uow.catalog.claim_due(self._clock.now(), limit=self._max_claim)
            await uow.commit()

        by_source: defaultdict[str, list[str]] = defaultdict(list)
        for listing in due:
            by_source[listing.source_id].append(listing.external_id)

        for source_id, external_ids in by_source.items():
            for start in range(0, len(external_ids), self._batch_size):
                await self._queue.enqueue(
                    jobs.COLLECT_LISTINGS,
                    lock=jobs.source_lock(source_id),
                    source_id=source_id,
                    external_ids=external_ids[start : start + self._batch_size],
                )
        return len(due)
