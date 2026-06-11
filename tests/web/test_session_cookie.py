from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware


def test_session_roundtrips():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    @app.get("/set")
    def set_it(request: Request):
        request.session["account_id"] = 7
        return {"ok": True}

    @app.get("/get")
    def get_it(request: Request):
        return {"account_id": request.session.get("account_id")}

    client = TestClient(app)
    client.get("/set")
    assert client.get("/get").json() == {"account_id": 7}
