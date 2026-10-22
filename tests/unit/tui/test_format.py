from datetime import UTC, datetime, timedelta

import pytest
from rich.console import Console

from caramelo.application.dashboard import QueueStats, SourceHealth
from caramelo.domain.ids import SourceId
from caramelo.domain.money import Price
from caramelo.entrypoints.tui import format as fmt

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def health(**changes: object) -> SourceHealth:
    fields: dict[str, object] = {
        "source_id": SourceId("kabum"),
        "monitored": 52,
        "sold_out": 11,
        "price_points": 57,
        "points_last_hour": 5,
        "last_collected_at": NOW - timedelta(minutes=2),
        "next_collect_at": NOW + timedelta(minutes=1),
        "overdue": 0,
        "estimated_requests_per_hour": 26.0,
    }
    fields.update(changes)
    return SourceHealth(**fields)  # type: ignore[arg-type]


def plain(renderable: object) -> str:
    console = Console(width=100, record=True, force_terminal=False)
    console.print(renderable)
    return console.export_text()


class TestRelative:
    @pytest.mark.parametrize(
        ("delta", "expected"),
        [
            (timedelta(seconds=10), "agora"),
            (-timedelta(seconds=40), "agora"),
            (-timedelta(minutes=2), "há 2 min"),
            (timedelta(minutes=1), "em 1 min"),
            (-timedelta(hours=3), "há 3 h"),
            (timedelta(hours=2), "em 2 h"),
            (-timedelta(days=4), "há 4 d"),
        ],
    )
    def test_formats_past_and_future(self, delta: timedelta, expected: str) -> None:
        assert fmt.relative(NOW, NOW + delta) == expected

    def test_missing_value(self) -> None:
        assert fmt.relative(NOW, None) == "—"


class TestChange:
    def test_a_price_drop_is_green(self) -> None:
        text = fmt.change(-0.083)

        assert text.plain == "▼ 8,3%"
        assert text.style == "green"

    def test_a_price_rise_is_red(self) -> None:
        text = fmt.change(0.1)

        assert text.plain == "▲ 10,0%"
        assert text.style == "red"

    @pytest.mark.parametrize("ratio", [None, 0.0, 0.0001, -0.0002])
    def test_no_real_change_is_a_dash(self, ratio: float | None) -> None:
        assert fmt.change(ratio).plain == "—"


def test_price_formatting() -> None:
    assert fmt.price(Price(209999)) == "R$ 2.099,99"
    assert fmt.price(None) == "—"


class TestHealthState:
    def test_collecting_when_recent_and_on_time(self) -> None:
        assert fmt.health_state(health(), NOW) == ("coletando", "green")

    def test_late_listings_make_it_late(self) -> None:
        assert fmt.health_state(health(overdue=3), NOW) == ("atrasado", "red")

    def test_stalled_when_nothing_was_collected_for_a_while(self) -> None:
        stale = health(last_collected_at=NOW - timedelta(hours=1))

        assert fmt.health_state(stale, NOW) == ("parado", "red")

    def test_waiting_for_the_first_collection(self) -> None:
        assert fmt.health_state(health(last_collected_at=None), NOW) == ("aguardando", "yellow")

    def test_nothing_monitored(self) -> None:
        assert fmt.health_state(health(monitored=0), NOW) == ("sem anúncios", "dim")


class TestQueueState:
    def test_up_to_date(self) -> None:
        assert fmt.queue_state(QueueStats(2, 1, 0, NOW), NOW) == ("em dia", "green")

    def test_failures_are_highlighted(self) -> None:
        assert fmt.queue_state(QueueStats(0, 0, 2, None), NOW) == ("2 falha(s)", "red")

    def test_old_pending_jobs_mean_a_backlog(self) -> None:
        backlog = QueueStats(9, 0, 0, NOW - timedelta(minutes=20))

        assert fmt.queue_state(backlog, NOW) == ("fila acumulada", "yellow")


class TestRenderOverview:
    def test_shows_each_store_and_the_queue(self) -> None:
        text = plain(fmt.render_overview([health()], QueueStats(0, 0, 0, None), NOW))

        assert "kabum" in text
        assert "● coletando" in text
        assert "anúncios monitorados" in text and "52" in text
        assert "há 2 min" in text and "em 1 min" in text
        assert "~26 requisições/hora" in text
        assert "fila de jobs" in text and "● em dia" in text

    def test_empty_database_explains_what_to_do(self) -> None:
        text = plain(fmt.render_overview([], QueueStats(0, 0, 0, None), NOW))

        assert "caramelo seed" in text
