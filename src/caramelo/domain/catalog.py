"""Product identity in three levels.

ProductFamily  -> what people search for   (RTX 4070 SUPER 12GB)
  Product      -> a concrete variant       (ASUS Dual RTX 4070 SUPER OC)
    Listing    -> that variant at a store  (Kabum SKU 123456)
"""

from dataclasses import dataclass

from caramelo.domain.ids import FamilyId, ListingId, ProductId, SourceId


@dataclass(slots=True)
class ProductFamily:
    id: FamilyId
    name: str
    category: str


@dataclass(slots=True)
class Product:
    id: ProductId
    brand: str
    name: str
    family_id: FamilyId | None = None
    mpn: str | None = None
    ean: str | None = None


@dataclass(slots=True)
class Listing:
    id: ListingId
    source_id: SourceId
    external_id: str
    url: str
    title: str
    # Filled by product matching; unmatched listings still collect history.
    product_id: ProductId | None = None
    monitored: bool = True
