import argparse
import asyncio
import logging

from caramelo.adapters.persistence import migrate
from caramelo.adapters.queue import procrastinate as queue
from caramelo.entrypoints.container import build_container
from caramelo.entrypoints.settings import Settings


async def _migrate(settings: Settings) -> None:
    # Alembic runs sync; keep it off the event loop.
    await asyncio.to_thread(migrate.upgrade, settings.sqlalchemy_url)
    app = queue.build_app(settings.database_url, handlers={})
    async with app.open_async():
        await queue.ensure_schema(app)


async def _worker(settings: Settings) -> None:
    container = build_container(settings)
    app = queue.build_app(settings.database_url, container.job_handlers())
    try:
        async with app.open_async():
            await queue.run_worker(app)
    finally:
        await container.aclose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="caramelo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply database migrations and the job queue schema")
    commands.add_parser("worker", help="run the background job worker")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    match args.command:
        case "migrate":
            asyncio.run(_migrate(settings))
        case "worker":
            asyncio.run(_worker(settings))
