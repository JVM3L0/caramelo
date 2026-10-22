from datetime import UTC, datetime, timedelta

from rich.console import Console
from textual.widgets import DataTable, Input, Static, TabbedContent

from caramelo.application.dashboard import (
    ListingQuery,
    ListingRow,
    QueueStats,
    SourceHealth,
)
from caramelo.domain.ids import ListingId, SourceId, new_id
from caramelo.domain.money import Price
from caramelo.entrypoints.tui.app import DashboardApp
from tests.fakes import FakeClock

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def row(external_id: str, title: str, **changes: object) -> ListingRow:
    fields: dict[str, object] = {
        "listing_id": ListingId(new_id()),
        "source_id": SourceId("kabum"),
        "external_id": external_id,
        "title": title,
        "url": f"https://kabum.test/{external_id}",
        "pix": Price(209999),
        "card": Price(247058),
        "in_stock": True,
        "collected_at": NOW - timedelta(minutes=3),
        "points": 2,
        "next_collect_at": NOW + timedelta(hours=1),
        "change": -0.083,
    }
    fields.update(changes)
    return ListingRow(**fields)  # type: ignore[arg-type]


class FakeQueries:
    """Serves canned data and remembers the listing queries it received."""

    def __init__(self, rows: list[ListingRow]) -> None:
        self.rows = rows
        self.queries: list[ListingQuery] = []
        self.failing = False

    async def source_health(
        self, now: datetime, overdue_after: timedelta = timedelta(minutes=10)
    ) -> list[SourceHealth]:
        if self.failing:
            raise ConnectionError("database is down")
        return [
            SourceHealth(SourceId("kabum"), 52, 11, 57, 5, NOW - timedelta(minutes=2), NOW, 0, 26.0)
        ]

    async def listings(self, query: ListingQuery) -> list[ListingRow]:
        self.queries.append(query)
        return [r for r in self.rows if query.search.lower() in r.title.lower()]


class FakeQueue:
    async def stats(self) -> QueueStats:
        return QueueStats(0, 0, 0, None)


def build(rows: list[ListingRow]) -> tuple[DashboardApp, FakeQueries]:
    queries = FakeQueries(rows)
    app = DashboardApp(queries, FakeQueue(), FakeClock(NOW, step=timedelta(0)), 3600)
    return app, queries


def overview_text(app: DashboardApp) -> str:
    console = Console(width=100, record=True, force_terminal=False)
    console.print(app.query_one("#overview-box", Static).content)
    return console.export_text()


async def settle(app: DashboardApp, pilot) -> None:  # type: ignore[no-untyped-def]
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_shows_the_overview_and_the_listings() -> None:
    app, _ = build([row("1", "Placa Husky RTX 3060"), row("2", "SSD Kingston 1TB")])

    async with app.run_test(size=(140, 40)) as pilot:
        await settle(app, pilot)

        assert "● coletando" in overview_text(app)
        assert "anúncios monitorados" in overview_text(app)
        assert app.query_one(DataTable).row_count == 2
        assert app.sub_title.startswith("atualizado às")


async def test_number_keys_switch_tabs() -> None:
    app, _ = build([row("1", "Placa")])

    async with app.run_test(size=(140, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("2")
        assert app.query_one(TabbedContent).active == "listings"
        await pilot.press("1")
        assert app.query_one(TabbedContent).active == "overview"


async def test_searching_filters_the_listings() -> None:
    app, queries = build([row("1", "Placa Husky RTX 3060"), row("2", "SSD Kingston 1TB")])

    async with app.run_test(size=(140, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("slash")
        await pilot.press(*"kingston")
        await settle(app, pilot)

        assert app.query_one("#search", Input).has_focus
        assert queries.queries[-1].search == "kingston"
        assert app.query_one(DataTable).row_count == 1


async def test_filter_keys_change_the_query() -> None:
    app, queries = build([row("1", "Placa")])

    async with app.run_test(size=(140, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("e")
        await settle(app, pilot)
        assert queries.queries[-1].in_stock is True
        await pilot.press("e")
        await settle(app, pilot)
        assert queries.queries[-1].in_stock is False
        await pilot.press("e")
        await settle(app, pilot)
        assert queries.queries[-1].in_stock is None

        await pilot.press("m")
        await settle(app, pilot)
        assert queries.queries[-1].changed_only is True

        await pilot.press("o")
        await settle(app, pilot)
        assert queries.queries[-1].order == "price"


async def test_a_database_failure_is_shown_and_the_last_data_is_kept() -> None:
    app, queries = build([row("1", "Placa")])

    async with app.run_test(size=(140, 40)) as pilot:
        await settle(app, pilot)
        queries.failing = True
        await pilot.press("r")
        await settle(app, pilot)

        banner = app.query_one("#error", Static)
        assert banner.display
        assert "database is down" in str(banner.content)
        assert app.query_one(DataTable).row_count == 1  # still showing the last good data

        queries.failing = False
        await pilot.press("r")
        await settle(app, pilot)
        assert not app.query_one("#error", Static).display


async def test_the_cursor_stays_on_the_same_listing_after_a_refresh() -> None:
    rows = [row("1", "Aaa"), row("2", "Bbb"), row("3", "Ccc")]
    app, _ = build(rows)

    async with app.run_test(size=(140, 40)) as pilot:
        await settle(app, pilot)
        await pilot.press("2")
        table = app.query_one(DataTable)
        table.focus()
        await pilot.press("down", "down")
        await pilot.pause()
        assert table.cursor_row == 2

        await pilot.press("r")
        await settle(app, pilot)

        assert table.cursor_row == 2


async def test_sold_out_listings_are_marked() -> None:
    app, _ = build([row("1", "Esgotada", in_stock=False, pix=None, card=None, change=None)])

    async with app.run_test(size=(140, 40)) as pilot:
        await settle(app, pilot)
        cells = app.query_one(DataTable).get_row_at(0)

        assert "esgotado" in str(cells[5])
        assert str(cells[2]) == "—"
