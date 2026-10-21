from datetime import UTC, datetime

from caramelo.adapters.copywriting.template import TemplateCopyWriter
from caramelo.domain.catalog import Listing
from caramelo.domain.ids import ListingId, SourceId, new_id
from caramelo.domain.money import Price
from caramelo.domain.offers import Deal
from caramelo.domain.pricing import PricePoint


async def test_template_shows_pix_and_installments() -> None:
    listing = Listing(
        id=ListingId(new_id()),
        source_id=SourceId("kabum"),
        external_id="1",
        url="https://kabum/1",
        title="RTX 4070 SUPER",
    )
    deal = Deal(
        listing,
        PricePoint(
            listing.id,
            datetime(2026, 10, 21, tzinfo=UTC),
            pix=Price.from_reais("4199.90"),
            card=Price.from_reais("4918.80"),
            installments=12,
            in_stock=True,
        ),
    )

    text = await TemplateCopyWriter().write(deal, "https://link")

    assert "💰 R$ 4.199,90 no Pix" in text
    assert "12x R$ 409,90" in text
    assert text.endswith("🛒 https://link")
