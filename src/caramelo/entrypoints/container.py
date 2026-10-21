from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from caramelo.adapters.affiliate.passthrough import PassthroughAffiliateLinker
from caramelo.adapters.clock import SystemClock
from caramelo.adapters.copywriting.template import TemplateCopyWriter
from caramelo.adapters.http.client import build_http_client
from caramelo.adapters.persistence.repositories import SqlUnitOfWork
from caramelo.application import jobs
from caramelo.application.jobs import JobHandler
from caramelo.application.ports import AffiliateLinker, Clock, CopyWriter, DealSource
from caramelo.application.use_cases.collect_source import CollectSource
from caramelo.domain.ids import SourceId
from caramelo.entrypoints.settings import Settings


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    http: httpx.AsyncClient
    clock: Clock
    affiliate: AffiliateLinker
    copywriter: CopyWriter
    # Store integrations register here as they are built (Kabum, Mercado Livre...).
    sources: dict[SourceId, DealSource] = field(default_factory=dict)

    def uow(self) -> SqlUnitOfWork:
        return SqlUnitOfWork(self.engine)

    def job_handlers(self) -> dict[str, JobHandler]:
        collect = CollectSource(self.uow, self.clock)

        async def collect_source(source_id: str) -> None:
            await collect(self.sources[SourceId(source_id)])

        return {jobs.COLLECT_SOURCE: collect_source}

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

    return Container(
        settings=settings,
        engine=create_async_engine(settings.sqlalchemy_url, pool_pre_ping=True),
        http=build_http_client(settings.http_user_agent, settings.http_proxy),
        clock=SystemClock(),
        affiliate=affiliate,
        copywriter=copywriter,
    )
