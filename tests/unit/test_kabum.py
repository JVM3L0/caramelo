import json
import re
from pathlib import Path

import httpx
import pytest

from caramelo.adapters.sources.http import Throttle
from caramelo.adapters.sources.kabum import (
    KabumSource,
    PageNotParsable,
    SourceBlocked,
    parse_product_page,
)
from caramelo.domain.money import Price

FIXTURE = Path(__file__).parent.parent / "fixtures" / "kabum_product.html"


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


def source(handler: httpx.MockTransport) -> tuple[KabumSource, list[float]]:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    client = httpx.AsyncClient(transport=handler, follow_redirects=True)
    return KabumSource(client, Throttle(0, sleep=sleep)), waits


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

    async def test_removed_products_are_skipped(self) -> None:
        kabum, _ = source(httpx.MockTransport(lambda r: httpx.Response(404)))

        assert [o async for o in kabum.fetch(["1"])] == []

    @pytest.mark.parametrize("status", [403, 429])
    async def test_blocking_raises_so_the_job_retries(self, status: int) -> None:
        kabum, _ = source(httpx.MockTransport(lambda r: httpx.Response(status)))

        with pytest.raises(SourceBlocked):
            [o async for o in kabum.fetch(["1"])]

    async def test_verification_redirect_counts_as_blocked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.startswith("/produto/"):
                return httpx.Response(302, headers={"location": "/gz/account-verification"})
            return httpx.Response(200, text="<html></html>")

        kabum, _ = source(httpx.MockTransport(handler))

        with pytest.raises(SourceBlocked):
            [o async for o in kabum.fetch(["1"])]

    async def test_server_errors_raise(self) -> None:
        kabum, _ = source(httpx.MockTransport(lambda r: httpx.Response(503)))

        with pytest.raises(httpx.HTTPStatusError):
            [o async for o in kabum.fetch(["1"])]

    async def test_every_request_goes_through_the_throttle(self) -> None:
        kabum, _ = source(httpx.MockTransport(lambda r: httpx.Response(404)))
        throttled: list[int] = []
        original = kabum._throttle.wait

        async def counting_wait() -> None:
            throttled.append(1)
            await original()

        kabum._throttle.wait = counting_wait  # type: ignore[method-assign]

        [o async for o in kabum.fetch(["1", "2", "3"])]

        assert len(throttled) == 3
