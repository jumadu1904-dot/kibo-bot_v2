from fastapi import FastAPI
from fastapi.testclient import TestClient

from kibo.web.routes import router


def test_health():
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).get("/health").json() == {"status": "ok"}
