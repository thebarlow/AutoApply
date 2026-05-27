import importlib
import sys
import pytest


def _fresh():
    """Reload module so each test starts with a zeroed accumulator."""
    if "core.session_cost" in sys.modules:
        del sys.modules["core.session_cost"]
    import core.session_cost as m
    return m


def test_initial_total_is_zero():
    m = _fresh()
    assert m.get_total() == 0.0


def test_add_cost_accumulates():
    m = _fresh()
    m.add_cost(0.001)
    m.add_cost(0.002)
    assert abs(m.get_total() - 0.003) < 1e-10


def test_add_cost_zero_is_noop():
    m = _fresh()
    m.add_cost(0.0)
    assert m.get_total() == 0.0


def test_reset_clears_total():
    m = _fresh()
    m.add_cost(1.5)
    m.reset()
    assert m.get_total() == 0.0


def test_thread_safety():
    import threading
    m = _fresh()
    threads = [threading.Thread(target=lambda: m.add_cost(1.0)) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert abs(m.get_total() - 100.0) < 1e-6
