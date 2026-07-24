from fastapi import FastAPI
from starlette.testclient import TestClient

from web.middleware_request_context import RequestContextMiddleware
from core import log_context


def _app():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    def ping():
        # Context is bound during the request; capture it.
        return log_context.snapshot()

    return app


def test_binds_request_id_and_route_and_sets_header():
    client = TestClient(_app())
    resp = client.get("/ping")
    body = resp.json()
    assert body["request_id"]
    assert body["route"] == "/ping"
    assert resp.headers["x-request-id"] == body["request_id"]


def test_context_cleared_after_request():
    client = TestClient(_app())
    client.get("/ping")
    assert log_context.snapshot()["request_id"] is None
