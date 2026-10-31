"""Pacing: requests per rolling minute and the concurrency cap."""

from __future__ import annotations

import threading
import time

from field_return_triage.llm.pacing import Pacer


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_third_request_in_a_minute_waits_for_the_window() -> None:
    fake = FakeClock()
    pacer = Pacer(
        max_concurrency=1,
        requests_per_minute=2,
        clock=fake.clock,
        sleeper=fake.sleep,
    )
    for _ in range(3):
        with pacer.slot():
            pass

    assert fake.sleeps == [60.0]
    assert fake.now == 60.0


def test_no_wait_when_the_window_has_room() -> None:
    fake = FakeClock()
    pacer = Pacer(
        max_concurrency=2,
        requests_per_minute=30,
        clock=fake.clock,
        sleeper=fake.sleep,
    )
    with pacer.slot():
        fake.now += 1.0
    with pacer.slot():
        pass
    assert fake.sleeps == []


def test_slots_release_and_allow_the_next_request() -> None:
    pacer = Pacer(max_concurrency=1, requests_per_minute=30)
    with pacer.slot():
        pass
    with pacer.slot():
        pass


def test_concurrency_cap_blocks_a_second_holder() -> None:
    pacer = Pacer(max_concurrency=1, requests_per_minute=30)
    entered = threading.Event()
    finished = threading.Event()

    def worker() -> None:
        with pacer.slot():
            entered.set()
        finished.set()

    with pacer.slot():
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.05)
        assert not entered.is_set()
    thread.join(timeout=2)
    assert finished.is_set()
