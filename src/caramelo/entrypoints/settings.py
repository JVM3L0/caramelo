from datetime import timedelta
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict

from caramelo.adapters.persistence import to_sqlalchemy_url
from caramelo.entrypoints.durations import parse_duration


def _duration(value: Any) -> Any:
    """Accepts 30m / 2h / 1d; ISO 8601 (PT30M) and non-strings are left to pydantic."""
    if isinstance(value, str) and not value.upper().startswith("P"):
        return parse_duration(value)
    return value


Duration = Annotated[timedelta, BeforeValidator(_duration)]


class Settings(BaseSettings):
    """Read from CARAMELO_* environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_prefix="CARAMELO_", env_file=".env", extra="ignore")

    # libpq form; procrastinate uses it as-is, SQLAlchemy gets the psycopg variant.
    database_url: str = "postgresql://caramelo:caramelo@localhost:5432/caramelo"

    # Identifies the bot honestly; stores can contact us through the repository.
    http_user_agent: str = "CarameloBot/0.2 (+https://github.com/JVM3L0/caramelo; price monitor)"
    # Off for the MVP; set e.g. http://user:pass@host:port to route store traffic.
    http_proxy: str | None = None

    # Collection pacing. Per-listing intervals can override the default.
    default_collect_interval: Duration = timedelta(hours=1)
    # Interval given to products found by `caramelo seed` (kept gentle on purpose).
    seed_collect_interval: Duration = timedelta(hours=2)
    # Minimum pause between two requests to the same store.
    request_min_interval: float = 2.0
    # How long a store is left alone after it blocks us (a Retry-After header wins).
    source_block_cooldown: Duration = timedelta(minutes=30)

    # How often the terminal dashboard re-reads the database, in seconds.
    dashboard_refresh_seconds: float = 5.0

    # Pluggable choices: add a value here plus a branch in the container.
    affiliate_linker: Literal["passthrough"] = "passthrough"
    copywriter: Literal["template"] = "template"

    @property
    def sqlalchemy_url(self) -> str:
        return to_sqlalchemy_url(self.database_url)
