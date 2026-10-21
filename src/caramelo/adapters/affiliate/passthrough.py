from caramelo.domain.ids import TenantId


class PassthroughAffiliateLinker:
    """Affiliate links are off for now: posts carry the store's original URL."""

    async def link(self, tenant_id: TenantId, url: str) -> str:
        return url
