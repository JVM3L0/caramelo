import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from caramelo.adapters.sources.http import Throttle
from caramelo.adapters.sources.kabum import (
    InvalidCategory,
    KabumSource,
    PageNotParsable,
    SourceBlocked,
    normalize_category,
    parse_category_page,
    parse_product_page,
)
from caramelo.domain.money import Price
from tests.fakes import FakeClock

FIXTURE = Path(__file__).parent.parent / "fixtures" / "kabum_product.html"
CATEGORY_FIXTURE = Path(__file__).parent.parent / "fixtures" / "kabum_category.html"
# Inside the real campaign window of the fixture (startsAt 1792589220, endsAt 1793019600).
DURING_OFFER = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
AFTER_OFFER = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def page(**changes: object) -> str:
    """The real product page with some payload fields overridden."""
    html = FIXTURE.read_text()
    match = re.search(r'(<script id="__NEXT_DATA__"[^>]*>)(.*?)(</script>)', html, re.S)
    assert match
    data = json.loads(match.group(2))
    data["props"]["pageProps"]["product"].update(changes)
    return html.replace(match.group(2), json.dumps(data, ensure_ascii=False))


class TestParseProductPage:
    def test_reads_prices_installments_and_identity(self) -> None:
        offer = parse_product_page(FIXTURE.read_text())

        assert offer.source_id == "kabum"
        assert offer.external_id == "996572"
        assert offer.pix == Price.from_reais("2099.99")
        assert offer.card == Price.from_reais("2470.58")
        assert offer.installments == 10
        assert offer.in_stock
        assert offer.seller == "KaBuM!"
        assert offer.title.startswith("Placa De Vídeo Husky Alpha RTX 3060")
        assert offer.url.startswith("https://www.kabum.com.br/produto/996572/")

    def test_sold_out_per_json_ld_is_out_of_stock(self) -> None:
        html = FIXTURE.read_text().replace("schema.org/InStock", "schema.org/OutOfStock")

        assert not parse_product_page(html).in_stock

    def test_unavailable_flag_is_out_of_stock(self) -> None:
        assert not parse_product_page(page(available=False)).in_stock

    def test_zero_prices_become_none(self) -> None:
        html = page(available=False, prices={"price": 0, "priceWithDiscount": 0, "oldPrice": 0})

        offer = parse_product_page(html)

        assert offer.pix is None
        assert offer.card is None

    def test_in_stock_without_a_price_is_an_error(self) -> None:
        with pytest.raises(PageNotParsable, match="without any price"):
            parse_product_page(page(prices={"price": 0, "priceWithDiscount": 0}))

    def test_marketplace_seller_is_kept(self) -> None:
        assert parse_product_page(page(sellerName="CELLFY")).seller == "CELLFY"

    @pytest.mark.parametrize("html", ["<html></html>", "<script id='__NEXT_DATA__'>{}</script>"])
    def test_unexpected_layout_is_an_error(self, html: str) -> None:
        with pytest.raises(PageNotParsable):
            parse_product_page(html)


class Clocks:
    """A controllable monotonic clock for cooldown tests."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class CountingThrottle(Throttle):
    """A throttle that never sleeps and counts how many requests asked to go out."""

    def __init__(self) -> None:
        super().__init__(0)
        self.requests = 0

    async def wait(self) -> None:
        self.requests += 1


def source(
    handler: httpx.MockTransport, monotonic: Clocks | None = None
) -> tuple[KabumSource, CountingThrottle]:
    throttle = CountingThrottle()
    client = httpx.AsyncClient(transport=handler, follow_redirects=True)
    kabum = KabumSource(client, throttle, FakeClock(DURING_OFFER), monotonic=monotonic or Clocks())
    return kabum, throttle


class TestExternalIdFromUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.kabum.com.br/produto/996572",
            "https://www.kabum.com.br/produto/996572/placa-de-video-husky",
            "http://kabum.com.br/produto/996572?utm_source=x",
        ],
    )
    def test_recognizes_product_urls(self, url: str) -> None:
        assert (
            source(httpx.MockTransport(lambda r: httpx.Response(500)))[0].external_id_from_url(url)
            == "996572"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.kabum.com.br/hardware/placa-de-video-vga",
            "https://www.kabum.com.br/carrinho",
            "https://www.mercadolivre.com.br/produto/123",
            "https://kabum.com.br.evil.test/produto/1",
        ],
    )
    def test_rejects_everything_else(self, url: str) -> None:
        assert (
            source(httpx.MockTransport(lambda r: httpx.Response(500)))[0].external_id_from_url(url)
            is None
        )


class TestFetch:
    async def test_follows_the_redirect_and_parses(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/produto/996572":
                return httpx.Response(301, headers={"location": "/produto/996572/slug"})
            return httpx.Response(200, text=FIXTURE.read_text())

        kabum, _ = source(httpx.MockTransport(handler))

        offers = [o async for o in kabum.fetch(["996572"])]

        assert [o.external_id for o in offers] == ["996572"]

    async def test_each_redirect_hop_goes_through_the_throttle(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/produto/996572":
                return httpx.Response(301, headers={"location": "/produto/996572/slug"})
            return httpx.Response(200, text=FIXTURE.read_text())

        kabum, throttle = source(httpx.MockTransport(handler))

        [o async for o in kabum.fetch(["996572"])]

        assert throttle.requests == 2  # the redirect and the page: two real requests

    async def test_the_redirected_url_is_remembered(self) -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(request.url.path)
            if request.url.path == "/produto/996572":
                return httpx.Response(301, headers={"location": "/produto/996572/slug"})
            return httpx.Response(200, text=FIXTURE.read_text())

        kabum, _ = source(httpx.MockTransport(handler))

        [o async for o in kabum.fetch(["996572"])]
        [o async for o in kabum.fetch(["996572"])]

        assert requested == ["/produto/996572", "/produto/996572/slug", "/produto/996572/slug"]

    async def test_redirect_loops_and_foreign_hosts_are_errors(self) -> None:
        loop = httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"location": "/produto/1"})
        )
        foreign = httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"location": "https://evil.test/x"})
        )

        for transport in (loop, foreign):
            kabum, _ = source(transport)
            with pytest.raises(PageNotParsable):
                [o async for o in kabum.fetch(["1"])]

    async def test_removed_products_are_skipped(self) -> None:
        kabum, _ = source(httpx.MockTransport(lambda r: httpx.Response(404)))

        assert [o async for o in kabum.fetch(["1"])] == []

    @pytest.mark.parametrize("status", [403, 429])
    async def test_blocking_raises_so_the_job_retries(self, status: int) -> None:
        kabum, _ = source(httpx.MockTransport(lambda r: httpx.Response(status)))

        with pytest.raises(SourceBlocked):
            [o async for o in kabum.fetch(["1"])]

    async def test_verification_redirect_counts_as_blocked(self) -> None:
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(request.url.path)
            if request.url.path.startswith("/produto/"):
                return httpx.Response(302, headers={"location": "/gz/account-verification?go=x"})
            return httpx.Response(200, text="<html></html>")

        kabum, _ = source(httpx.MockTransport(handler))

        with pytest.raises(SourceBlocked):
            [o async for o in kabum.fetch(["1"])]
        # the forbidden verification page is never requested
        assert requested == ["/produto/1"]

    async def test_server_errors_raise(self) -> None:
        kabum, _ = source(httpx.MockTransport(lambda r: httpx.Response(503)))

        with pytest.raises(httpx.HTTPStatusError):
            [o async for o in kabum.fetch(["1"])]

    async def test_every_request_goes_through_the_throttle(self) -> None:
        kabum, throttle = source(httpx.MockTransport(lambda r: httpx.Response(404)))

        [o async for o in kabum.fetch(["1", "2", "3"])]

        assert throttle.requests == 3


class TestParseCategoryPage:
    def test_active_campaign_prices_replace_the_base_prices(self) -> None:
        offers, total_pages = parse_category_page(CATEGORY_FIXTURE.read_text(), DURING_OFFER)

        husky = next(o for o in offers if o.external_id == "996572")
        assert total_pages == 8
        assert husky.pix == Price.from_reais("2099.99")  # offer.priceWithDiscount
        assert husky.card == Price.from_reais("2470.58")  # offer.price
        assert husky.installments == 10
        assert husky.in_stock
        assert husky.url.startswith("https://www.kabum.com.br/produto/996572/placa-de-video-husky")

    def test_after_the_campaign_the_base_prices_apply(self) -> None:
        offers, _ = parse_category_page(CATEGORY_FIXTURE.read_text(), AFTER_OFFER)

        husky = next(o for o in offers if o.external_id == "996572")
        assert husky.pix == Price.from_reais("2999.99")
        assert husky.card == Price.from_reais("3529.40")

    def test_sold_out_items_keep_their_prices_but_are_out_of_stock(self) -> None:
        offers, _ = parse_category_page(CATEGORY_FIXTURE.read_text(), DURING_OFFER)

        msi = next(o for o in offers if o.external_id == "997882")
        assert not msi.in_stock  # `available` is true, the quantity is 0
        assert msi.pix == Price.from_reais("2699.99")

    def test_marketplace_sellers_are_left_out(self) -> None:
        offers, _ = parse_category_page(CATEGORY_FIXTURE.read_text(), DURING_OFFER)

        assert {o.external_id for o in offers} == {"996572", "997882"}
        assert {o.seller for o in offers} == {"KaBuM!"}

    def test_prime_exclusive_campaigns_are_not_public_prices(self) -> None:
        html = CATEGORY_FIXTURE.read_text().replace(
            r"\"isPrimeExclusive\": null", r"\"isPrimeExclusive\": true"
        )

        offers, _ = parse_category_page(html, DURING_OFFER)

        husky = next(o for o in offers if o.external_id == "996572")
        assert husky.pix == Price.from_reais("2999.99")

    @pytest.mark.parametrize("html", ["<html></html>", "<script id='__NEXT_DATA__'>{}</script>"])
    def test_unexpected_layout_is_an_error(self, html: str) -> None:
        with pytest.raises(PageNotParsable):
            parse_category_page(html, DURING_OFFER)


class TestNormalizeCategory:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("hardware/placa-de-video-vga", "hardware/placa-de-video-vga"),
            ("/Hardware/SSD/", "hardware/ssd"),
            ("perifericos", "perifericos"),
        ],
    )
    def test_accepts_plain_catalog_paths(self, given: str, expected: str) -> None:
        assert normalize_category(given) == expected

    @pytest.mark.parametrize(
        "given",
        [
            "",
            "carrinho",
            "minha-conta/pedidos",
            "busca/rtx",
            "hardware?sort=price",
            "hardware/ssd?page_number=2",
            "../etc",
            "hardware//ssd",
            "https://www.kabum.com.br/hardware",
            "produto/123",
        ],
    )
    def test_rejects_anything_robots_txt_forbids_or_that_is_not_a_category(
        self, given: str
    ) -> None:
        with pytest.raises(InvalidCategory):
            normalize_category(given)


def category_handler(pages: int, requested: list[str]) -> httpx.MockTransport:
    """Serves the category fixture and records each requested URL."""

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        html = CATEGORY_FIXTURE.read_text().replace(r"\"total\": 8", rf"\"total\": {pages}")
        return httpx.Response(200, text=html)

    return httpx.MockTransport(handler)


class TestDiscover:
    async def test_reads_one_page_by_default_url(self) -> None:
        requested: list[str] = []
        kabum, _ = source(category_handler(8, requested))

        offers = [o async for o in kabum.discover("hardware/placa-de-video-vga", 1)]

        assert requested == ["https://www.kabum.com.br/hardware/placa-de-video-vga"]
        assert len(offers) == 2

    async def test_follows_pages_up_to_the_requested_limit(self) -> None:
        requested: list[str] = []
        kabum, _ = source(category_handler(8, requested))

        [o async for o in kabum.discover("hardware/ssd", 3)]

        assert requested == [
            "https://www.kabum.com.br/hardware/ssd",
            "https://www.kabum.com.br/hardware/ssd?page_number=2&page_size=60",
            "https://www.kabum.com.br/hardware/ssd?page_number=3&page_size=60",
        ]

    async def test_stops_at_the_last_page_of_the_category(self) -> None:
        requested: list[str] = []
        kabum, _ = source(category_handler(2, requested))

        [o async for o in kabum.discover("hardware/ssd", 5)]

        assert len(requested) == 2

    async def test_never_exceeds_the_hard_page_cap(self) -> None:
        requested: list[str] = []
        kabum, _ = source(category_handler(500, requested))

        [o async for o in kabum.discover("hardware/ssd", 10_000)]

        assert len(requested) == 10

    async def test_invalid_category_makes_no_request(self) -> None:
        requested: list[str] = []
        kabum, _ = source(category_handler(1, requested))

        with pytest.raises(InvalidCategory):
            [o async for o in kabum.discover("carrinho", 1)]
        assert requested == []

    async def test_unknown_category_is_an_error(self) -> None:
        kabum, _ = source(httpx.MockTransport(lambda r: httpx.Response(404)))

        with pytest.raises(PageNotParsable, match="not found"):
            [o async for o in kabum.discover("hardware/nao-existe", 1)]


class TestBlockCooldown:
    @staticmethod
    def blocking_store(requested: list[str], **headers: str) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(429, headers=headers)

        return httpx.MockTransport(handler)

    async def test_after_a_block_the_store_is_left_alone(self) -> None:
        requested: list[str] = []
        kabum, _ = source(self.blocking_store(requested))

        with pytest.raises(SourceBlocked, match="blocked"):
            [o async for o in kabum.fetch(["1"])]
        for _ in range(3):
            with pytest.raises(SourceBlocked, match="cooling down"):
                [o async for o in kabum.fetch(["2"])]
        with pytest.raises(SourceBlocked, match="cooling down"):
            [o async for o in kabum.discover("hardware/ssd", 1)]

        assert len(requested) == 1

    async def test_requests_resume_once_the_cooldown_is_over(self) -> None:
        requested: list[str] = []
        monotonic = Clocks()
        kabum, _ = source(self.blocking_store(requested), monotonic)

        with pytest.raises(SourceBlocked):
            [o async for o in kabum.fetch(["1"])]
        monotonic.now += 31 * 60  # default cooldown is 30 minutes
        with pytest.raises(SourceBlocked, match="blocked"):
            [o async for o in kabum.fetch(["1"])]

        assert len(requested) == 2

    async def test_retry_after_header_sets_the_cooldown(self) -> None:
        requested: list[str] = []
        monotonic = Clocks()
        kabum, _ = source(self.blocking_store(requested, **{"retry-after": "7200"}), monotonic)

        with pytest.raises(SourceBlocked):
            [o async for o in kabum.fetch(["1"])]
        monotonic.now += 3600  # past the default 30 min, still inside Retry-After
        with pytest.raises(SourceBlocked, match="cooling down"):
            [o async for o in kabum.fetch(["1"])]

        assert len(requested) == 1

    async def test_retry_after_is_capped(self) -> None:
        requested: list[str] = []
        monotonic = Clocks()
        kabum, _ = source(
            self.blocking_store(requested, **{"retry-after": str(30 * 24 * 3600)}), monotonic
        )

        with pytest.raises(SourceBlocked):
            [o async for o in kabum.fetch(["1"])]
        monotonic.now += 6 * 3600 + 1

        with pytest.raises(SourceBlocked, match="blocked"):
            [o async for o in kabum.fetch(["1"])]
        assert len(requested) == 2

    def test_blocks_and_layout_errors_are_not_retried(self) -> None:
        assert SourceBlocked("x").retryable is False
        assert PageNotParsable("x").retryable is False
        assert InvalidCategory("x").retryable is False
