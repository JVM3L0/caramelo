from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from caramelo.adapters.persistence import to_sqlalchemy_url


class Settings(BaseSettings):
    """Read from CARAMELO_* environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_prefix="CARAMELO_", env_file=".env", extra="ignore")

    # libpq form; procrastinate uses it as-is, SQLAlchemy gets the psycopg variant.
    database_url: str = "postgresql://caramelo:caramelo@localhost:5432/caramelo"

    http_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0 Safari/537.36"
    )
    # Off for the MVP; set e.g. http://user:pass@host:port to route store traffic.
    http_proxy: str | None = None

    # Pluggable choices: add a value here plus a branch in the container.
    affiliate_linker: Literal["passthrough"] = "passthrough"
    copywriter: Literal["template"] = "template"

    @property
    def sqlalchemy_url(self) -> str:
        return to_sqlalchemy_url(self.database_url)
