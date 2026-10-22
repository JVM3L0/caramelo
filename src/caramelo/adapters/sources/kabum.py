"""Kabum integration, built on public pages that robots.txt allows.

- Product page (/produto/<code>): the embedded Next.js payload, with the schema.org
  JSON-LD as the stock cross-check. `prices.price` is the card price and
  `prices.priceWithDiscount` the Pix price; both already reflect an active campaign.
- Category page (/<category>?page_number=N): the same kind of payload, 60 products per
  request, used to discover products and to read their first prices cheaply. There the
  base prices sit on the item and an active campaign's prices sit under `offer`. The item's
  `quantity` is the stock of the *campaign*, not of the product: products outside any
  campaign have 0 and are still on sale (their product page says "Comprar", InStock).

Rate limiting: every request goes through the shared Throttle, and a block (403, 429 or
the verification page) puts the source in a cooldown during which no request is made.
"""

import json
import re
import time
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, NoReturn
from urllib.parse import urljoin

import httpx
from selectolax.lexbor import LexborHTMLParser

from caramelo.adapters.sources.http import Throttle
from caramelo.application.jobs import JobFailure
from caramelo.application.ports import Clock
from caramelo.domain.ids import SourceId
from caramelo.domain.money import Price
from caramelo.domain.offers import RawOffer

SOURCE_ID = SourceId("kabum")
BASE_URL = "https://www.kabum.com.br"
OWN_STORE = "KaBuM!"

PAGE_SIZE = 60
MAX_PAGES = 10  # hard cap per discovery, whatever the caller asks for
MAX_REDIRECTS = 3
DEFAULT_BLOCK_COOLDOWN = timedelta(minutes=30)
MAX_BLOCK_COOLDOWN = timedelta(hours=6)  # ceiling for a server-provided Retry-After

_PRODUCT_URL = re.compile(r"^https?://(?:www\.)?kabum\.com\.br/produto/(\d+)(?:[/?#]|$)")
_CATEGORY_PATH = re.compile(r"^[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*){0,3}$")
_INSTALLMENTS = re.compile(r"^\s*(\d+)\s*x", re.IGNORECASE)
# First path segments that robots.txt disallows or that are not categories at all.
_NOT_CATEGORIES = frozenset(
    {
        "busca",
        "carrinho",
        "cgi-local",
        "conteudo",
        "destaques",
        "kabum3",
        "lancamentos",
        "link",
        "login",
        "manager",
        "minha-conta",
        "precarrinho",
        "produto",
    }
)


class SourceError(JobFailure):
    """The store answered, but not with usable data."""


class SourceBlocked(SourceError):
    """The store is challenging us (verification page, 403 or 429).

    Not retried: the listings are rescheduled for their next slot, and the source
    stays quiet during its cooldown instead of being hit again.
    """

    retryable = False


class PageNotParsable(SourceError):
    """The page layout changed or the payload is missing. Retrying would not help."""

    retryable = False


class InvalidCategory(SourceError, ValueError):
    """The category path is not one we are willing to request. Retrying would not help."""

    retryable = False


def normalize_category(category: str) -> str:
    """Validates a category path such as 'hardware/placa-de-video-vga'.

    Only plain catalog paths are accepted, so nothing the robots.txt forbids (search,
    cart, account, sorted listings, query strings) can be requested through here.
    """
    path = category.strip().strip("/").lower()
    if not _CATEGORY_PATH.match(path) or path.split("/")[0] in _NOT_CATEGORIES:
        raise InvalidCategory(f"not a valid Kabum category path: {category!r}")
    return path


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


def _active_offer(item: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    offer = item.get("offer")
    if not offer or offer.get("isPrimeExclusive"):  # membership-only prices are not public
        return None
    if offer.get("quantityAvailable") == 0:  # campaign sold out: the base price applies
        return None
    if offer["startsAt"] <= now.timestamp() <= offer["endsAt"]:
        return offer
    return None


def parse_category_page(html: str, now: datetime) -> tuple[list[RawOffer], int]:
    """Offers sold by Kabum itself on one category page, and the category's page count.

    Marketplace sellers are left out: their prices follow other rules and the first
    version only publishes what the store sells directly.
    """
    node = LexborHTMLParser(html).css_first("script#__NEXT_DATA__")
    if node is None:
        raise PageNotParsable("no __NEXT_DATA__ payload")
    try:
        # The catalog is a JSON document serialized inside the Next.js payload.
        raw = json.loads(node.text())["props"]["pageProps"]["data"]
        catalog = json.loads(raw, parse_float=Decimal)["catalogServer"]
        items = catalog["data"]
        total_pages = int(catalog["pagination"]["total"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise PageNotParsable(f"unexpected catalog shape: {exc!r}") from exc

    offers: list[RawOffer] = []
    for item in items:
        try:
            if item["flags"].get("isMarketplace") or item["sellerName"] != OWN_STORE:
                continue
            offer = _active_offer(item, now)
            source = offer or item
            installments = _INSTALLMENTS.match(item.get("maxInstallment") or "")
            offers.append(
                RawOffer(
                    source_id=SOURCE_ID,
                    external_id=str(item["code"]),
                    url=f"{BASE_URL}/produto/{item['code']}/{item['friendlyName']}",
                    title=item["name"],
                    pix=_price(source.get("priceWithDiscount")),
                    card=_price(source.get("price")),
                    installments=int(installments.group(1)) if installments else None,
                    # `quantity` is the campaign's stock, so it says nothing about the product.
                    in_stock=bool(item.get("available")),
                    seller=item["sellerName"],
                )
            )
        except (KeyError, TypeError) as exc:
            raise PageNotParsable(f"unexpected item shape: {exc!r}") from exc
    return offers, total_pages


def _retry_after(response: httpx.Response) -> timedelta | None:
    value = response.headers.get("retry-after", "")
    return timedelta(seconds=int(value)) if value.isdigit() else None


class KabumSource:
    def __init__(
        self,
        client: httpx.AsyncClient,
        throttle: Throttle,
        clock: Clock,
        block_cooldown: timedelta = DEFAULT_BLOCK_COOLDOWN,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._throttle = throttle
        self._clock = clock
        self._block_cooldown = block_cooldown
        self._monotonic = monotonic
        self._blocked_until = 0.0
        # Product URLs after their redirect, so later collections skip the extra hop.
        self._canonical_urls: dict[str, str] = {}

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

    async def discover(self, category: str, max_pages: int) -> AsyncIterator[RawOffer]:
        path = normalize_category(category)
        for page in range(1, min(max_pages, MAX_PAGES) + 1):
            url = f"{BASE_URL}/{path}"
            if page > 1:
                url += f"?page_number={page}&page_size={PAGE_SIZE}"
            response = await self._get(url)
            if response.status_code in (404, 410):
                raise PageNotParsable(f"category not found: {path}")
            offers, total_pages = parse_category_page(response.text, self._clock.now())
            for offer in offers:
                self._canonical_urls[offer.external_id] = offer.url
                yield offer
            if page >= total_pages:
                return

    async def _fetch_one(self, external_id: str) -> RawOffer | None:
        url = self._canonical_urls.get(external_id, f"{BASE_URL}/produto/{external_id}")
        response = await self._get(url)
        if response.status_code in (404, 410):
            self._canonical_urls.pop(external_id, None)
            return None  # product removed from the store
        self._canonical_urls[external_id] = str(response.url)
        return parse_product_page(response.text)

    async def _get(self, url: str) -> httpx.Response:
        """The single door to the store: cooldown check, then throttled requests.

        Redirects are followed here, one throttled request per hop, so the real request
        rate is the configured one and a redirect to the verification page (which
        robots.txt forbids) is never requested. 404/410 are returned for the caller to
        interpret; other errors raise.
        """
        remaining = self._blocked_until - self._monotonic()
        if remaining > 0:
            raise SourceBlocked(f"kabum is cooling down for {remaining:.0f}s more")

        for _ in range(MAX_REDIRECTS + 1):
            await self._throttle.wait()
            response = await self._client.get(url, follow_redirects=False)
            if response.is_redirect:
                url = urljoin(str(response.url), response.headers.get("location", ""))
                if "account-verification" in url:
                    self._block(response, 403)
                if not url.startswith(BASE_URL + "/"):
                    raise PageNotParsable(f"redirected outside kabum: {url}")
                continue
            if response.status_code in (403, 429):
                self._block(response, response.status_code)
            if response.status_code not in (404, 410):
                response.raise_for_status()
            return response
        raise PageNotParsable("too many redirects")

    def _block(self, response: httpx.Response, status: int) -> NoReturn:
        cooldown = min(_retry_after(response) or self._block_cooldown, MAX_BLOCK_COOLDOWN)
        self._blocked_until = self._monotonic() + cooldown.total_seconds()
        raise SourceBlocked(f"kabum blocked the request ({status}); pausing for {cooldown}")
