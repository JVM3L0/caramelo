"""Terminal charts (plotext). They only draw what the queries already returned."""

from datetime import datetime

from textual_plotext import PlotextPlot

from caramelo.application.dashboard import ActivityBucket, ListingHistory

DATE_FORM = "d/m/Y H:M"


def _local(moment: datetime) -> datetime:
    return moment.astimezone().replace(tzinfo=None)


def step_points[T](series: list[tuple[datetime, T]]) -> list[tuple[datetime, T]]:
    """Turns collections into a step line: a store price holds until it changes, so each
    value is carried up to the moment of the next collection instead of sloping towards it."""
    stepped: list[tuple[datetime, T]] = []
    for index, (moment, value) in enumerate(series):
        if index > 0:
            stepped.append((moment, series[index - 1][1]))
        stepped.append((moment, value))
    return stepped


class PriceChart(PlotextPlot):
    """Pix and card price of one listing over time. Sold-out collections are left out."""

    shown = 0  # number of collections drawn, useful for tests

    def show(self, history: ListingHistory | None) -> None:
        plt = self.plt
        plt.clear_figure()
        self.shown = 0
        points = [p for p in history.points if p.in_stock] if history else []
        if history is None or not any(p.pix or p.card for p in points):
            plt.title("sem preço no período")
            self.refresh()
            return

        plt.date_form(DATE_FORM)
        for label, getter in (("Pix", lambda p: p.pix), ("Cartão", lambda p: p.card)):
            series = [(p.collected_at, getter(p)) for p in points if getter(p) is not None]
            if not series:
                continue
            if len(series) == 1:
                moment, value = series[0]
                plt.scatter(
                    [plt.datetime_to_string(_local(moment))], [value.cents / 100], label=label
                )
                continue
            stepped = step_points(series)
            plt.plot(
                [plt.datetime_to_string(_local(moment)) for moment, _ in stepped],
                [value.cents / 100 for _, value in stepped],
                label=label,
                marker="braille",
            )
        self.shown = len(points)
        plt.title(history.title[:70])
        plt.ylabel("R$")
        self.refresh()


class ActivityChart(PlotextPlot):
    """Price points collected per hour: a quick read on whether the worker is steady."""

    total = 0

    def show(self, buckets: list[ActivityBucket]) -> None:
        plt = self.plt
        plt.clear_figure()
        self.total = sum(b.points for b in buckets)
        labels = [f"{b.hour.astimezone():%H}h" for b in buckets]
        plt.bar(labels, [b.points for b in buckets])
        plt.title(f"Pontos de preço por hora (últimas {len(buckets)} h): {self.total}")
        self.refresh()
