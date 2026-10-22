"""Kabum integration: reads the public product page (/produto/<code>).

Only product pages are requested; robots.txt allows them. The data comes from the
page's embedded Next.js payload, with the schema.org JSON-LD as the stock cross-check.
Prices on the page: `prices.price` is the card price, `prices.priceWithDiscount` is the
Pix price, and both already reflect an active campaign.
"""

import json
import re
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal
from typing import Any

import httpx
from selectolax.lexbor import LexborHTMLParser

from caramelo.adapters.sources.http import Throttle
from caramelo.domain.ids import SourceId
from caramelo.domain.money import Price
from caramelo.domain.offers import RawOffer

SOURCE_ID = SourceId("kabum")
BASE_URL = "https://www.kabum.com.br"
OWN_STORE = "KaBuM!"

_PRODUCT_URL = re.compile(r"^https?://(?:www\.)?kabum\.com\.br/produto/(\d+)(?:[/?#]|$)")


class SourceError(Exception):
    """The store answered, but not with usable data. Raising makes the job retry."""


class SourceBlocked(SourceError):
    """The store is challenging us (verification page, 403 or 429)."""


class PageNotParsable(SourceError):
    """The page layout changed or the payload is missing."""


def _price(value: Any) -> Price | None:
    if value in (None, 0, "0"):
        return None
    return Price.from_reais(Decimal(str(value)))


def _json_ld_product(tree: LexborHTMLParser) -> dict[str, Any]:
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return {}


def parse_product_page(html: str) -> RawOffer:
    tree = LexborHTMLParser(html)
    node = tree.css_first("script#__NEXT_DATA__")
    if node is None:
        raise PageNotParsable("no __NEXT_DATA__ payload")
    try:
        # Decimal avoids float noise such as 2470.5800000000002.
        payload = json.loads(node.text(), parse_float=Decimal)
        product = payload["props"]["pageProps"]["product"]
        prices = product["prices"]
        external_id = str(product["id"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise PageNotParsable(f"unexpected payload shape: {exc!r}") from exc

    ld = _json_ld_product(tree)
    availability = str(ld.get("offers", {}).get("availability", ""))
    # `available` alone is not enough: sold-out items can keep it true.
    in_stock = bool(product.get("available")) and not availability.endswith("OutOfStock")

    pix, card = _price(prices.get("priceWithDiscount")), _price(prices.get("price"))
    if in_stock and pix is None and card is None:
        raise PageNotParsable("in-stock product without any price")

    installment = product.get("installment") or {}
    friendly = product.get("friendlyName")
    url = ld.get("offers", {}).get("url") or (
        f"{BASE_URL}/produto/{external_id}/{friendly}"
        if friendly
        else f"{BASE_URL}/produto/{external_id}"
    )
    return RawOffer(
        source_id=SOURCE_ID,
        external_id=external_id,
        url=url,
        title=ld.get("name") or product["title"],
        pix=pix,
        card=card,
        installments=installment.get("installment"),
        in_stock=in_stock,
        seller=product.get("sellerName") or OWN_STORE,
    )


class KabumSource:
    def __init__(self, client: httpx.AsyncClient, throttle: Throttle) -> None:
        self._client = client
        self._throttle = throttle

    @property
    def id(self) -> SourceId:
        return SOURCE_ID

    def external_id_from_url(self, url: str) -> str | None:
        match = _PRODUCT_URL.match(url)
        return match.group(1) if match else None

    async def fetch(self, external_ids: Sequence[str]) -> AsyncIterator[RawOffer]:
        for external_id in external_ids:
            offer = await self._fetch_one(external_id)
            if offer is not None:
                yield offer

    async def _fetch_one(self, external_id: str) -> RawOffer | None:
        await self._throttle.wait()
        response = await self._client.get(f"{BASE_URL}/produto/{external_id}")
        if response.status_code in (404, 410):
            return None  # product removed from the store
        if response.status_code in (403, 429) or "account-verification" in str(response.url):
            raise SourceBlocked(f"kabum blocked the request ({response.status_code})")
        response.raise_for_status()
        return parse_product_page(response.text)
