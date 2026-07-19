import threading
import pytest
from datetime import datetime, timezone
import core.session_cost as sc


@pytest.fixture(autouse=True)
def reset_cost():
    sc.reset()
    yield
    sc.reset()


def test_initial_total_is_zero():
    assert sc.get_total() == 0.0


def test_add_cost_accumulates():
    sc.add_cost(0.001)
    sc.add_cost(0.002)
    assert abs(sc.get_total() - 0.003) < 1e-10


def test_add_cost_zero_is_noop():
    sc.add_cost(0.0)
    assert sc.get_total() == 0.0


def test_reset_clears_total():
    sc.add_cost(1.5)
    sc.reset()
    assert sc.get_total() == 0.0


def test_thread_safety():
    threads = [threading.Thread(target=lambda: sc.add_cost(1.0)) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert abs(sc.get_total() - 100.0) < 1e-6


