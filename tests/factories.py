from caramelo.domain.ids import SourceId
from caramelo.domain.money import Price
from caramelo.domain.offers import RawOffer


def raw_offer(external_id: str = "123", **overrides: object) -> RawOffer:
    fields: dict[str, object] = {
        "source_id": SourceId("kabum"),
        "external_id": external_id,
        "url": f"https://www.kabum.com.br/produto/{external_id}",
        "title": "Placa de Vídeo ASUS Dual RTX 4070 SUPER OC 12GB",
        "pix": Price.from_reais("4199.90"),
        "card": Price.from_reais("4918.80"),
        "installments": 12,
        "in_stock": True,
    }
    fields.update(overrides)
    return RawOffer(**fields)  # type: ignore[arg-type]
