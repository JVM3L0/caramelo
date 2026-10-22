"""Pure helpers that turn query results into what the dashboard shows."""

from datetime import datetime, timedelta

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from caramelo.application.dashboard import QueueStats, SourceHealth
from caramelo.domain.money import Price

# No collection for this long means the worker is not doing its job.
STALE_AFTER = timedelta(minutes=30)


def price(value: Price | None) -> str:
    return "—" if value is None else str(value)


def percent(ratio: float) -> str:
    return f"{abs(ratio) * 100:.1f}".replace(".", ",") + "%"


def change(ratio: float | None) -> Text:
    """A price drop is good news (green), a rise is not (red)."""
    if ratio is None or abs(ratio) < 0.0005:
        return Text("—", style="dim")
    if ratio < 0:
        return Text(f"▼ {percent(ratio)}", style="green")
    return Text(f"▲ {percent(ratio)}", style="red")


def relative(now: datetime, then: datetime | None) -> str:
    """'há 2 min', 'em 1 h', 'agora'."""
    if then is None:
        return "—"
    delta = (then - now).total_seconds()
    seconds = abs(delta)
    if seconds < 45:
        return "agora"
    minutes = round(seconds / 60)
    if minutes < 60:
        amount = f"{minutes} min"
    elif minutes < 60 * 48:
        amount = f"{round(minutes / 60)} h"
    else:
        amount = f"{round(minutes / (60 * 24))} d"
    return f"em {amount}" if delta > 0 else f"há {amount}"


def health_state(health: SourceHealth, now: datetime) -> tuple[str, str]:
    """(label, rich style) summarizing whether a store's collection is on track."""
    if health.monitored == 0:
        return "sem anúncios", "dim"
    if health.overdue > 0:
        return "atrasado", "red"
    if health.last_collected_at is None:
        return "aguardando", "yellow"
    if now - health.last_collected_at > STALE_AFTER:
        return "parado", "red"
    return "coletando", "green"


def queue_state(queue: QueueStats, now: datetime) -> tuple[str, str]:
    if queue.failed:
        return f"{queue.failed} falha(s)", "red"
    if queue.oldest_pending_at and now - queue.oldest_pending_at > timedelta(minutes=5):
        return "fila acumulada", "yellow"
    return "em dia", "green"


def render_overview(health: list[SourceHealth], queue: QueueStats, now: datetime) -> RenderableType:
    if not health:
        return Panel(
            Text("Nenhum anúncio coletado ainda. Use `caramelo seed` ou `caramelo watch`."),
            title="Visão geral",
        )
    panels: list[RenderableType] = []
    for source in health:
        label, style = health_state(source, now)
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim")
        grid.add_column()
        grid.add_column(style="dim")
        grid.add_column()
        grid.add_row(
            "anúncios monitorados",
            str(source.monitored),
            "última coleta",
            relative(now, source.last_collected_at),
        )
        grid.add_row(
            "esgotados agora",
            str(source.sold_out),
            "próxima coleta",
            relative(now, source.next_collect_at),
        )
        grid.add_row(
            "pontos de preço",
            str(source.price_points),
            "pontos na última hora",
            str(source.points_last_hour),
        )
        grid.add_row(
            "atrasados",
            Text(str(source.overdue), style="red" if source.overdue else ""),
            "carga estimada",
            f"~{source.estimated_requests_per_hour:.0f} requisições/hora",
        )
        panels.append(
            Panel(grid, title=f"{source.source_id}  [{style}]● {label}[/]", title_align="left")
        )

    queue_label, queue_style = queue_state(queue, now)
    jobs = Table.grid(padding=(0, 2))
    jobs.add_column(style="dim")
    jobs.add_column()
    jobs.add_column(style="dim")
    jobs.add_column()
    jobs.add_row("pendentes", str(queue.pending), "em execução", str(queue.running))
    jobs.add_row(
        "falhas (total)",
        Text(str(queue.failed), style="red" if queue.failed else ""),
        "mais antigo pendente",
        relative(now, queue.oldest_pending_at),
    )
    panels.append(
        Panel(jobs, title=f"fila de jobs  [{queue_style}]● {queue_label}[/]", title_align="left")
    )
    return Group(*panels)
