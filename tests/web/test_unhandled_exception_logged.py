import asyncio
import logging


def test_unhandled_exception_is_logged(caplog):
    from web.main import _log_unhandled_exception

    class Boom(Exception):
        pass

    req = type("R", (), {"scope": {"path": "/api/x"}})()
    # A prior test in the full suite may import alembic's env.py, whose
    # logging.config.fileConfig() call disables loggers that already existed
    # (disable_existing_loggers defaults to True). Re-enable ours defensively
    # so this test is order-independent.
    logging.getLogger("web.unhandled").disabled = False
    with caplog.at_level(logging.ERROR):
        try:
            asyncio.run(_log_unhandled_exception(req, Boom("kaboom")))
        except Boom:
            pass
    assert any("kaboom" in r.getMessage() or r.exc_info for r in caplog.records)
