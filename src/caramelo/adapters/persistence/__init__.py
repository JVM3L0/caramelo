"""Postgres + TimescaleDB persistence (SQLAlchemy Core, Alembic migrations)."""


def to_sqlalchemy_url(database_url: str) -> str:
    """Converts a libpq URL (postgresql://...) into one bound to the psycopg 3 driver."""
    scheme, sep, rest = database_url.partition("://")
    if scheme not in ("postgres", "postgresql"):
        return database_url
    return f"postgresql+psycopg{sep}{rest}"
