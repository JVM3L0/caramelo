import argparse
import asyncio
import logging
from datetime import timedelta

from caramelo.adapters.persistence import migrate
from caramelo.adapters.queue import procrastinate as queue
from caramelo.application import jobs
from caramelo.domain.ids import SourceId
from caramelo.entrypoints import durations
from caramelo.entrypoints.container import build_container
from caramelo.entrypoints.settings import Settings


def parse_duration(text: str) -> timedelta:
    try:
        return durations.parse_duration(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


MAX_SEED_PAGES = 10
PRODUCTS_PER_PAGE = 60


def describe_seed(category: str, pages: int, every: timedelta, request_min_interval: float) -> str:
    """What a seed will cost the store, shown before anything is sent to it."""
    products = pages * PRODUCTS_PER_PAGE
    per_hour = products * timedelta(hours=1) / every
    return (
        f"descoberta de '{category}': até {pages} requisição(ões), uma a cada "
        f"{request_min_interval:g}s no mínimo, e até {products} produtos.\n"
        f"depois cada produto é coletado a cada {every}: ~{per_hour:.0f} requisições/hora "
        f"no total, espalhadas ao longo do intervalo."
    )


async def _migrate(settings: Settings) -> None:
    # Alembic runs sync; keep it off the event loop.
    await asyncio.to_thread(migrate.upgrade, settings.sqlalchemy_url)
    app = queue.create_app(settings.database_url)
    async with app.open_async():
        await queue.ensure_schema(app)


async def _worker(settings: Settings) -> None:
    container = build_container(settings)
    container.register_jobs()
    try:
        async with container.queue_app.open_async():
            await queue.run_worker(container.queue_app)
    finally:
        await container.aclose()


async def _watch(settings: Settings, url: str, every: timedelta) -> None:
    container = build_container(settings)
    try:
        monitored = await container.monitor_listing()(url, every)
    finally:
        await container.aclose()
    print(f"monitorando: {monitored.listing.title}")
    print(f"a cada {every}; preço atual: {monitored.first_price.best}")


async def _seed(
    settings: Settings, source_id: str, category: str, pages: int, every: timedelta
) -> None:
    container = build_container(settings)
    try:
        if SourceId(source_id) not in container.sources:
            known = ", ".join(sorted(container.sources))
            raise SystemExit(f"fonte desconhecida {source_id!r} (disponíveis: {known})")
        print(describe_seed(category, pages, every, settings.request_min_interval))
        async with container.queue_app.open_async():
            await container.task_queue.enqueue(
                jobs.DISCOVER_LISTINGS,
                lock=jobs.source_lock(source_id),
                source_id=source_id,
                category=category,
                max_pages=pages,
                interval_seconds=int(every.total_seconds()),
            )
    finally:
        await container.aclose()
    print(
        "enfileirado: o worker executa respeitando o ritmo da loja (acompanhe com `logs worker`)."
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="caramelo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply database migrations and the job queue schema")
    commands.add_parser("worker", help="run the background job worker")
    watch = commands.add_parser("watch", help="add a product URL to the monitored catalog")
    watch.add_argument("url")
    watch.add_argument("--every", type=parse_duration, help="collection interval, e.g. 30m, 2h")
    seed = commands.add_parser(
        "seed", help="find the products of a store category and monitor them (runs in the worker)"
    )
    seed.add_argument("source", help="store id, e.g. kabum")
    seed.add_argument("category", help="category path, e.g. hardware/placa-de-video-vga")
    seed.add_argument(
        "--pages",
        type=int,
        choices=range(1, MAX_SEED_PAGES + 1),
        default=1,
        help="category pages to read, 60 products each (default 1)",
    )
    seed.add_argument("--every", type=parse_duration, help="collection interval, e.g. 2h")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    match args.command:
        case "migrate":
            asyncio.run(_migrate(settings))
        case "worker":
            asyncio.run(_worker(settings))
        case "seed":
            every = args.every or settings.seed_collect_interval
            asyncio.run(_seed(settings, args.source, args.category, args.pages, every))
        case "watch":
            every = args.every or settings.default_collect_interval
            asyncio.run(_watch(settings, args.url, every))
