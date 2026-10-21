from caramelo.domain.money import Price
from caramelo.domain.offers import Deal


class TemplateCopyWriter:
    """Fixed-format post text. An LLM-backed CopyWriter can replace it later."""

    async def write(self, deal: Deal, url: str) -> str:
        point = deal.price
        lines = [deal.listing.title, ""]
        if point.pix is not None:
            lines.append(f"💰 {point.pix} no Pix")
        if point.card is not None:
            if point.installments and point.installments > 1:
                per_month = Price(round(point.card.cents / point.installments))
                lines.append(f"💳 {point.installments}x {per_month} ({point.card} no cartão)")
            else:
                lines.append(f"💳 {point.card} no cartão")
        lines += [f"🏪 {deal.listing.source_id}", "", f"🛒 {url}"]
        return "\n".join(lines)
