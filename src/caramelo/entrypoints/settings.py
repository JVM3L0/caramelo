from datetime import timedelta
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from caramelo.adapters.persistence import to_sqlalchemy_url


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
    default_collect_interval: timedelta = timedelta(hours=1)
    # Minimum pause between two requests to the same store.
    request_min_interval: float = 2.0

    # Pluggable choices: add a value here plus a branch in the container.
    affiliate_linker: Literal["passthrough"] = "passthrough"
    copywriter: Literal["template"] = "template"

    @property
    def sqlalchemy_url(self) -> str:
        return to_sqlalchemy_url(self.database_url)
