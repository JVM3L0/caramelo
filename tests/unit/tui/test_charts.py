from datetime import UTC, datetime, timedelta

from caramelo.entrypoints.tui.charts import step_points

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def at(hours: int) -> datetime:
    return T0 + timedelta(hours=hours)


def test_a_price_holds_until_the_next_collection() -> None:
    series = [(at(0), 100), (at(2), 90), (at(5), 90)]

    assert step_points(series) == [
        (at(0), 100),
        (at(2), 100),  # still 100 right up to the second collection...
        (at(2), 90),  # ...where it drops
        (at(5), 90),
        (at(5), 90),
    ]


def test_a_single_collection_stays_a_single_point() -> None:
    assert step_points([(at(0), 100)]) == [(at(0), 100)]


def test_no_collections_draw_nothing() -> None:
    assert step_points([]) == []
