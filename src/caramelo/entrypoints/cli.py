import argparse
import asyncio
import logging
import re
from datetime import timedelta

from caramelo.adapters.persistence import migrate
from caramelo.adapters.queue import procrastinate as queue
from caramelo.entrypoints.container import build_container
from caramelo.entrypoints.settings import Settings

_DURATION = re.compile(r"(\d+)([mhd])")
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    """Parses values like 30m, 2h, 1d or 1h30m."""
    parts = _DURATION.findall(text)
    if not parts or "".join(n + u for n, u in parts) != text:
        raise argparse.ArgumentTypeError(f"invalid duration {text!r} (use e.g. 30m, 2h, 1d)")
    return sum((timedelta(**{_UNITS[u]: int(n)}) for n, u in parts), timedelta())


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="caramelo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply database migrations and the job queue schema")
    commands.add_parser("worker", help="run the background job worker")
    watch = commands.add_parser("watch", help="add a product URL to the monitored catalog")
    watch.add_argument("url")
    watch.add_argument("--every", type=parse_duration, help="collection interval, e.g. 30m, 2h")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    match args.command:
        case "migrate":
            asyncio.run(_migrate(settings))
        case "worker":
            asyncio.run(_worker(settings))
        case "watch":
            every = args.every or settings.default_collect_interval
            asyncio.run(_watch(settings, args.url, every))
