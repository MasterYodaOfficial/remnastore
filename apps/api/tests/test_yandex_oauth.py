import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from app.api.v1.endpoints.yandex import router
from app.core.config import settings


class YandexProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.config = patch.object(settings, "yandex_oauth_client_id", "our-client")
        self.config.start()
        self.addCleanup(self.config.stop)

    async def request(self, upstream, authorization="Bearer private-token"):
        def handler(request):
            self.assertEqual(
                str(request.url), "https://login.yandex.ru/info?format=json"
            )
            self.assertEqual(request.headers["Authorization"], "OAuth private-token")
            if isinstance(upstream, Exception):
                raise upstream
            return upstream

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        ) as client:
            upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            with patch(
                "app.api.v1.endpoints.yandex.httpx.AsyncClient",
                return_value=upstream_client,
            ):
                return await client.get(
                    "/yandex/userinfo", headers={"Authorization": authorization}
                )

    async def test_translates_profile_without_claiming_email_is_verified(self):
        response = await self.request(
            httpx.Response(
                200,
                json={
                    "client_id": "our-client",
                    "id": "123",
                    "default_email": "a@yandex.ru",
                    "real_name": "Test User",
                    "login": "test",
                    "sex": "male",
                },
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "sub": "123",
                "email": "a@yandex.ru",
                "email_verified": False,
                "name": "Test User",
                "preferred_username": "test",
            },
        )
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_rejects_token_for_another_app(self):
        response = await self.request(
            httpx.Response(
                200,
                json={
                    "client_id": "another-client",
                    "id": "123",
                    "default_email": "a@yandex.ru",
                },
            )
        )
        self.assertEqual(response.status_code, 401)

    async def test_missing_email_or_subject_does_not_create_identity(self):
        for profile, expected in [
            ({"client_id": "our-client", "id": "123"}, 422),
            ({"client_id": "our-client", "default_email": "a@yandex.ru"}, 502),
            ([], 502),
        ]:
            response = await self.request(httpx.Response(200, json=profile))
            self.assertEqual(response.status_code, expected)

    async def test_upstream_failure_does_not_leak_response(self):
        for status, expected in [(401, 401), (403, 401), (500, 502), (302, 502)]:
            response = await self.request(httpx.Response(status, text="private-token"))
            self.assertEqual(response.status_code, expected)
            self.assertNotIn("private-token", response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_malformed_upstream_response_is_not_exposed(self):
        response = await self.request(httpx.Response(200, text="private-token"))
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-token", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_upstream_timeout_is_retryable_without_exposing_token(self):
        response = await self.request(httpx.ReadTimeout("private-token"))
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-token", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_rejects_missing_or_wrong_authorization(self):
        for header in ["", "Basic private-token", "Bearer ", "Bearer two tokens"]:
            response = await self.request(httpx.Response(200), header)
            self.assertEqual(response.status_code, 401)

    async def test_disabled_without_client_id(self):
        with patch.object(settings, "yandex_oauth_client_id", ""):
            response = await self.request(httpx.Response(200))
        self.assertEqual(response.status_code, 503)
