from caramelo.adapters.sources.http import Throttle


async def test_spaces_requests_by_the_minimum_interval() -> None:
    now = 100.0
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        nonlocal now
        slept.append(seconds)
        now += seconds

    throttle = Throttle(2.0, clock=lambda: now, sleep=sleep)

    await throttle.wait()  # first request goes right away
    await throttle.wait()
    now += 5  # idle longer than the interval
    await throttle.wait()

    assert slept == [2.0]
