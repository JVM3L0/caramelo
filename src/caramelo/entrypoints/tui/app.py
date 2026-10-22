from dataclasses import replace
from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import DataTable, Footer, Header, Input, Static, TabbedContent, TabPane

from caramelo.application.dashboard import (
    LISTING_ORDERS,
    DashboardQueries,
    ListingQuery,
    ListingRow,
    QueueStatistics,
)
from caramelo.application.ports import Clock
from caramelo.entrypoints.tui import format as fmt

ORDER_LABELS = {
    "recent": "mais recentes",
    "price": "menor preço",
    "change": "maiores quedas",
    "title": "nome",
}
STOCK_LABELS = {None: "todos", True: "só em estoque", False: "só esgotados"}
TITLE_WIDTH = 52


class DashboardApp(App[None]):
    """Shows how the collection is going. Everything it displays comes from the database."""

    TITLE = "Caramelo"
    CSS = """
    #error { background: $error 30%; color: $text; padding: 0 1; display: none; }
    #overview-box { padding: 1 2; }
    #filters { padding: 0 1; color: $text-muted; }
    #search { margin: 0 1; }
    DataTable { height: 1fr; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Sair"),
        Binding("r", "refresh", "Atualizar"),
        Binding("1", "show_tab('overview')", "Visão geral"),
        Binding("2", "show_tab('listings')", "Anúncios"),
        Binding("slash", "focus_search", "Buscar"),
        Binding("e", "cycle_stock", "Estoque"),
        Binding("m", "toggle_changed", "Só mudanças"),
        Binding("o", "cycle_order", "Ordem"),
    ]

    def __init__(
        self,
        queries: DashboardQueries,
        queue: QueueStatistics,
        clock: Clock,
        refresh_seconds: float = 5.0,
    ) -> None:
        super().__init__()
        self._queries = queries
        self._queue = queue
        self._clock = clock
        self._refresh_seconds = refresh_seconds
        self._query = ListingQuery()
        self._selected_key: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="error")
        with TabbedContent(initial="overview"):
            with TabPane("Visão geral", id="overview"):
                yield Static(id="overview-box")
            with TabPane("Anúncios", id="listings"):
                yield Input(placeholder="buscar por nome…  (/)", id="search")
                yield Static(id="filters")
                yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(
            "Loja", "Produto", "Pix", "Cartão", "Var.", "Estoque", "Coletas", "Atualizado"
        )
        self._update_filters_label()
        self.set_interval(self._refresh_seconds, self.action_refresh)
        self.action_refresh()

    # --- actions ---------------------------------------------------------

    def action_refresh(self) -> None:
        self.run_worker(self._reload(), exclusive=True, group="reload")

    def action_show_tab(self, tab: str) -> None:
        self.query_one(TabbedContent).active = tab

    def action_focus_search(self) -> None:
        self.action_show_tab("listings")
        self.query_one("#search", Input).focus()

    def action_cycle_stock(self) -> None:
        cycle = [None, True, False]
        nxt = cycle[(cycle.index(self._query.in_stock) + 1) % len(cycle)]
        self._change_query(in_stock=nxt)

    def action_toggle_changed(self) -> None:
        self._change_query(changed_only=not self._query.changed_only)

    def action_cycle_order(self) -> None:
        index = LISTING_ORDERS.index(self._query.order)
        self._change_query(order=LISTING_ORDERS[(index + 1) % len(LISTING_ORDERS)])

    @on(Input.Changed, "#search")
    def _search_changed(self, event: Input.Changed) -> None:
        self._change_query(search=event.value.strip())

    @on(DataTable.RowHighlighted)
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._selected_key = event.row_key.value if event.row_key else None

    # --- data ------------------------------------------------------------

    def _change_query(self, **changes: object) -> None:
        self._query = replace(self._query, **changes)  # type: ignore[arg-type]
        self._update_filters_label()
        self.action_refresh()

    def _update_filters_label(self) -> None:
        q = self._query
        self.query_one("#filters", Static).update(
            f"ordem: {ORDER_LABELS[q.order]} (o)   estoque: {STOCK_LABELS[q.in_stock]} (e)   "
            f"só mudanças: {'sim' if q.changed_only else 'não'} (m)"
        )

    async def _reload(self) -> None:
        try:
            now = self._clock.now()
            health = await self._queries.source_health(now)
            queue = await self._queue.stats()
            rows = await self._queries.listings(self._query)
        except Exception as exc:  # the database may be down; keep what is on screen
            self._show_error(f"não foi possível ler os dados: {exc}")
            return
        self._show_error(None)
        self.query_one("#overview-box", Static).update(fmt.render_overview(health, queue, now))
        self._fill_table(rows)
        self.sub_title = f"atualizado às {now.astimezone():%H:%M:%S}"

    def _show_error(self, message: str | None) -> None:
        banner = self.query_one("#error", Static)
        banner.display = message is not None
        banner.update(message or "")

    def _fill_table(self, rows: list[ListingRow]) -> None:
        table = self.query_one(DataTable)
        keep = self._selected_key
        table.clear()
        for row in rows:
            title = (
                row.title if len(row.title) <= TITLE_WIDTH else row.title[: TITLE_WIDTH - 1] + "…"
            )
            table.add_row(
                row.source_id,
                title,
                Text(fmt.price(row.pix), justify="right"),
                Text(fmt.price(row.card), justify="right"),
                fmt.change(row.change),
                Text("sim", style="green") if row.in_stock else Text("esgotado", style="red"),
                str(row.points),
                fmt.relative(self._clock.now(), row.collected_at),
                key=str(row.listing_id),
            )
        if keep is not None:
            try:
                table.move_cursor(row=table.get_row_index(keep))
            except Exception:  # the selected listing no longer matches the filters
                self._selected_key = None
