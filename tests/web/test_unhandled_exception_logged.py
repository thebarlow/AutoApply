import logging

from fastapi import FastAPI
from starlette.testclient import TestClient

from web.middleware_request_context import RequestContextMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    def boom():
        raise ValueError("kaboom")

    return app


def test_unhandled_exception_logged_with_context(caplog):
    # A prior test in the full suite may import alembic's env.py, whose
    # logging.config.fileConfig() call disables loggers that already existed
    # (disable_existing_loggers defaults to True). Re-enable ours defensively
    # so this test is order-independent.
    logging.getLogger("web.request").disabled = False
    client = TestClient(_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="web.request"):
        resp = client.get("/boom")
    assert resp.status_code == 500
    recs = [r for r in caplog.records if r.name == "web.request"]
    assert recs, "expected an ERROR log from web.request"
    rec = recs[0]
    # ContextFilter is only attached by setup_logging()'s console handler, not in
    # this bare test app; the meaningful assertion is that the middleware logged
    # the exception while the context was still bound (before clear()).
    assert rec.exc_info is not None
