import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_context import register_request_context_middleware
from common.logging_setup import get_request_id


class RequestContextMiddlewareTests(unittest.TestCase):
    def test_middleware_generates_request_id_and_exposes_header(self) -> None:
        app = FastAPI()
        register_request_context_middleware(app, emit_access_log=False)

        @app.get("/request-id")
        async def request_id_view() -> dict[str, str]:
            return {"request_id": get_request_id()}

        with TestClient(app) as client:
            response = client.get("/request-id")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["X-Request-ID"])
        self.assertEqual(response.json()["request_id"], response.headers["X-Request-ID"])

    def test_middleware_preserves_incoming_request_id(self) -> None:
        app = FastAPI()
        register_request_context_middleware(app, emit_access_log=False)

        @app.get("/request-id")
        async def request_id_view() -> dict[str, str]:
            return {"request_id": get_request_id()}

        with TestClient(app) as client:
            response = client.get("/request-id", headers={"X-Request-ID": "req-123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Request-ID"], "req-123")
        self.assertEqual(response.json()["request_id"], "req-123")


if __name__ == "__main__":
    unittest.main()
