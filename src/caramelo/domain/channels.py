from dataclasses import dataclass
from enum import StrEnum

from caramelo.domain.ids import ChannelId, TenantId


@dataclass(slots=True)
class Tenant:
    """A channel owner. The MVP has a single tenant; the SaaS adds more."""

    id: TenantId
    name: str


class ChannelKind(StrEnum):
    TELEGRAM = "telegram"


@dataclass(slots=True)
class Channel:
    id: ChannelId
    tenant_id: TenantId
    kind: ChannelKind
    name: str
    # Platform-specific destination, e.g. a Telegram chat id or @handle.
    target: str
    enabled: bool = True
