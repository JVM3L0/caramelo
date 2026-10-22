import logging
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
import procrastinate
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from caramelo.adapters.affiliate.passthrough import PassthroughAffiliateLinker
from caramelo.adapters.clock import SystemClock
from caramelo.adapters.copywriting.template import TemplateCopyWriter
from caramelo.adapters.persistence.dashboard import SqlDashboardQueries
from caramelo.adapters.persistence.repositories import SqlUnitOfWork
from caramelo.adapters.queue import procrastinate as queue
from caramelo.adapters.queue.stats import ProcrastinateQueueStatistics
from caramelo.adapters.sources.http import Throttle, build_http_client
from caramelo.adapters.sources.kabum import KabumSource
from caramelo.application import jobs
from caramelo.application.dashboard import DashboardQueries, QueueStatistics
from caramelo.application.jobs import JobHandler
from caramelo.application.ports import (
    AffiliateLinker,
    Clock,
    CopyWriter,
    DealSource,
    TaskQueue,
)
from caramelo.application.use_cases.collect_listings import CollectListings
from caramelo.application.use_cases.monitor_listing import MonitorListing
from caramelo.application.use_cases.schedule_collections import ScheduleDueCollections
from caramelo.application.use_cases.seed_catalog import SeedCatalog
from caramelo.domain.ids import SourceId
from caramelo.entrypoints.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    http: httpx.AsyncClient
    clock: Clock
    affiliate: AffiliateLinker
    copywriter: CopyWriter
    queue_app: procrastinate.App
    task_queue: TaskQueue
    # Store integrations, by source id.
    sources: dict[SourceId, DealSource] = field(default_factory=dict)

    def uow(self) -> SqlUnitOfWork:
        return SqlUnitOfWork(self.engine)

    def dashboard_queries(self) -> DashboardQueries:
        return SqlDashboardQueries(self.engine)

    def queue_statistics(self) -> QueueStatistics:
        return ProcrastinateQueueStatistics(self.queue_app)

    def monitor_listing(self) -> MonitorListing:
        return MonitorListing(self.sources, self.uow, self.clock)

    def job_handlers(self) -> dict[str, JobHandler]:
        collect = CollectListings(self.uow, self.clock)
        schedule = ScheduleDueCollections(self.uow, self.task_queue, self.clock)
        seed = SeedCatalog(self.uow, self.clock)

        async def collect_listings(source_id: str, external_ids: list[str]) -> None:
            await collect(self.sources[SourceId(source_id)], external_ids)

        async def discover_listings(
            source_id: str, category: str, max_pages: int, interval_seconds: int
        ) -> None:
            result = await seed(
                self.sources[SourceId(source_id)],
                category,
                max_pages,
                timedelta(seconds=interval_seconds),
            )
            logger.info("seeded %s/%s: %s", source_id, category, result)

        return {
            jobs.COLLECT_LISTINGS: collect_listings,
            jobs.DISCOVER_LISTINGS: discover_listings,
            jobs.SCHEDULE_DUE_COLLECTIONS: schedule,
        }

    def register_jobs(self) -> None:
        queue.register(self.queue_app, self.job_handlers(), periodic=jobs.PERIODIC)

    async def aclose(self) -> None:
        await self.http.aclose()
        await self.engine.dispose()


def build_container(settings: Settings) -> Container:
    match settings.affiliate_linker:
        case "passthrough":
            affiliate = PassthroughAffiliateLinker()
    match settings.copywriter:
        case "template":
            copywriter = TemplateCopyWriter()

    queue_app = queue.create_app(settings.database_url)
    http = build_http_client(settings.http_user_agent, settings.http_proxy)
    clock = SystemClock()
    kabum = KabumSource(
        http,
        Throttle(settings.request_min_interval),
        clock,
        block_cooldown=settings.source_block_cooldown,
    )
    return Container(
        settings=settings,
        engine=create_async_engine(settings.sqlalchemy_url, pool_pre_ping=True),
        http=http,
        clock=clock,
        affiliate=affiliate,
        copywriter=copywriter,
        queue_app=queue_app,
        task_queue=queue.ProcrastinateTaskQueue(queue_app),
        sources={kabum.id: kabum},
    )
