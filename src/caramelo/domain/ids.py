from typing import NewType
from uuid import UUID, uuid4

TenantId = NewType("TenantId", UUID)
ChannelId = NewType("ChannelId", UUID)
FamilyId = NewType("FamilyId", UUID)
ProductId = NewType("ProductId", UUID)
ListingId = NewType("ListingId", UUID)

# Stable slug of a store integration, e.g. "kabum" or "mercadolivre".
SourceId = NewType("SourceId", str)


def new_id() -> UUID:
    return uuid4()
