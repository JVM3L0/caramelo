import os

from alembic import context
from sqlalchemy import create_engine

from caramelo.adapters.persistence import to_sqlalchemy_url
from caramelo.adapters.persistence.tables import metadata

DEFAULT_URL = "postgresql://caramelo:caramelo@localhost:5432/caramelo"


def database_url() -> str:
    # Set programmatically by migrate.upgrade(); falls back to the env for the alembic CLI.
    url = context.config.get_main_option("sqlalchemy.url")
    return url or to_sqlalchemy_url(os.environ.get("CARAMELO_DATABASE_URL", DEFAULT_URL))


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
