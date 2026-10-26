import asyncio
import base64
import hashlib
import json
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from pydantic import SecretStr

from app.api.v1.endpoints.vk import router
from app.core.config import settings
from app.services import vk_oauth as oauth
from app.services.cache import OAuthStateUnavailable


SECRET = "test-bridge-secret-" + "x" * 32
CALLBACK = "https://api.example.test/api/v1/auth/vk/callback"
SUPABASE_CALLBACK = "https://auth.example.test/auth/v1/callback"
VERIFIER = "test-verifier-" + "x" * 43
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .decode()
    .rstrip("=")
)


class MemoryState:
    def __init__(self):
        self.values = {}
        self.now = 0

    async def set_oauth_json(self, key, value, ttl_seconds):
        assert key not in self.values
        self.values[key] = (json.loads(json.dumps(value)), self.now + ttl_seconds)

    async def get_oauth_json(self, key, *, consume=False):
        item = self.values.pop(key, None) if consume else self.values.get(key)
        return item[0] if item and item[1] > self.now else None


class VKOAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemoryState()
        self.app = FastAPI()
        self.app.include_router(router, prefix="/auth")
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="https://api.example.test",
        )
        self.addAsyncCleanup(self.client.aclose)
        self.config = patch.multiple(
            settings,
            vk_oauth_client_id="123456",
            vk_oauth_bridge_secret=SecretStr(SECRET),
            vk_oauth_callback_url=CALLBACK,
            vk_oauth_supabase_callback_url=SUPABASE_CALLBACK,
        )
        self.config.start()
        self.addCleanup(self.config.stop)
        self.cache = patch.object(oauth, "get_cache", return_value=self.store)
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def auth_params(self, **extra):
        return {
            "response_type": "code",
            "client_id": "123456",
            "redirect_uri": SUPABASE_CALLBACK,
            "state": "supabase-original-state",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            **extra,
        }

    async def begin(self):
        response = await self.client.get(
            "/auth/vk/authorize", params=self.auth_params()
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["cache-control"], "no-store")
        query = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual(query["redirect_uri"], [CALLBACK])
        self.assertEqual(query["code_challenge"], [CHALLENGE])
        self.assertNotEqual(query["state"], ["supabase-original-state"])
        return query["state"][0]

    async def code(self):
        state = await self.begin()
        response = await self.client.get(
            "/auth/vk/callback",
            params={
                "state": state,
                "code": "private-vk-code",
                "device_id": "private-device",
            },
        )
        self.assertEqual(response.status_code, 302)
        url = response.headers["location"]
        self.assertTrue(url.startswith(SUPABASE_CALLBACK + "?"))
        self.assertNotIn("private-vk-code", url)
        self.assertNotIn("private-device", url)
        self.assertEqual(
            parse_qs(urlsplit(url).query)["state"], ["supabase-original-state"]
        )
        return parse_qs(urlsplit(url).query)["code"][0], state

    def token_params(self, code, **extra):
        return {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SUPABASE_CALLBACK,
            "code_verifier": VERIFIER,
            "client_id": "123456",
            "client_secret": SECRET,
            **extra,
        }

    def upstream(self, state, *, email=True, subject="42", token_state=None):
        self.requests = []

        def handler(request):
            self.requests.append(request)
            data = parse_qs(request.content.decode())
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.host, "id.vk.ru")
            if request.url.path == "/oauth2/auth":
                self.assertEqual(data["code"], ["private-vk-code"])
                self.assertEqual(data["device_id"], ["private-device"])
                self.assertEqual(data["redirect_uri"], [CALLBACK])
                self.assertEqual(data["code_verifier"], [VERIFIER])
                self.assertNotIn("client_secret", data)
                return httpx.Response(
                    200,
                    json={
                        "user_id": 42,
                        "access_token": "private-vk-token",
                        "state": token_state or state,
                        "refresh_token": "private-refresh-token",
                    },
                )
            self.assertEqual(request.url.path, "/oauth2/user_info")
            self.assertEqual(data["access_token"], ["private-vk-token"])
            profile = {
                "user_id": subject,
                "first_name": "Test",
                "last_name": "User",
                "phone": "private-phone",
            }
            if email:
                profile["email"] = "client@example.test"
            return httpx.Response(200, json={"user": profile})

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def test_complete_flow_returns_only_opaque_profile_token_and_standard_claims(
        self,
    ):
        code, state = await self.code()
        with patch.object(
            oauth.httpx, "AsyncClient", return_value=self.upstream(state)
        ):
            response = await self.client.post(
                "/auth/vk/token", data=self.token_params(code)
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["expires_in"], oauth.TOKEN_TTL)
        for secret in (
            "private-vk-token",
            "private-refresh-token",
            "private-device",
            SECRET,
        ):
            self.assertNotIn(secret, response.text)
            self.assertNotIn(secret, json.dumps(self.store.values))
        self.assertEqual(len(self.requests), 2)
        token = response.json()["access_token"]
        response = await self.client.get(
            "/auth/vk/userinfo", headers={"Authorization": "Bearer " + token}
        )
        self.assertEqual(
            response.json(),
            {
                "sub": "42",
                "name": "Test User",
                "email": "client@example.test",
                "email_verified": False,
            },
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.store.now += oauth.TOKEN_TTL
        expired = await self.client.get(
            "/auth/vk/userinfo", headers={"Authorization": "Bearer " + token}
        )
        self.assertEqual(expired.status_code, 401)

    async def test_missing_email_is_supported_without_fabricating_verified_email(self):
        code, state = await self.code()
        with patch.object(
            oauth.httpx, "AsyncClient", return_value=self.upstream(state, email=False)
        ):
            response = await self.client.post(
                "/auth/vk/token", data=self.token_params(code)
            )
        claims = await oauth.userinfo("Bearer " + response.json()["access_token"])
        self.assertNotIn("email", claims)
        self.assertFalse(claims["email_verified"])

    async def test_untrusted_redirects_and_missing_pkce_never_redirect(self):
        for extra in (
            {"redirect_uri": "https://evil.test/callback"},
            {"client_id": "other-app"},
            {"code_challenge_method": "plain"},
            {"code_challenge": ""},
            {"state": ""},
        ):
            response = await self.client.get(
                "/auth/vk/authorize", params=self.auth_params(**extra)
            )
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("location", response.headers)
        self.assertEqual(self.store.values, {})

    async def test_state_is_one_time_and_expires(self):
        state = await self.begin()
        self.store.now += oauth.FLOW_TTL
        response = await self.client.get(
            "/auth/vk/callback", params={"state": state, "code": "c", "device_id": "d"}
        )
        self.assertEqual(response.status_code, 400)
        state = await self.begin()
        params = {"state": state, "code": "c", "device_id": "d"}
        responses = await asyncio.gather(
            *(self.client.get("/auth/vk/callback", params=params) for _ in range(2))
        )
        self.assertEqual(sorted(r.status_code for r in responses), [302, 400])

    async def test_cancellation_preserves_supabase_state_and_hides_provider_detail(
        self,
    ):
        state = await self.begin()
        response = await self.client.get(
            "/auth/vk/callback",
            params={
                "state": state,
                "error": "access_denied",
                "error_description": "private-vk-token",
            },
        )
        query = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual(query["error"], ["access_denied"])
        self.assertEqual(query["state"], ["supabase-original-state"])
        self.assertNotIn("private-vk-token", response.headers["location"])

    async def test_client_credentials_and_pkce_are_checked_before_consuming_code(self):
        code, _ = await self.code()
        for extra, status in (
            ({"client_secret": "wrong"}, 401),
            ({"code_verifier": "x" * 43}, 400),
            ({"redirect_uri": "https://evil.test"}, 400),
            ({"grant_type": "refresh_token"}, 400),
        ):
            response = await self.client.post(
                "/auth/vk/token", data=self.token_params(code, **extra)
            )
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertNotIn(SECRET, response.text)
            self.assertIsNotNone(await oauth.load("code", code))

    async def test_basic_authentication_and_authorization_code_replay(self):
        code, state = await self.code()
        params = self.token_params(code)
        del params["client_id"], params["client_secret"]
        headers = {
            "Authorization": "Basic "
            + base64.b64encode(("123456:" + SECRET).encode()).decode()
        }
        with patch.object(
            oauth.httpx, "AsyncClient", return_value=self.upstream(state)
        ):
            response = await self.client.post(
                "/auth/vk/token", data=params, headers=headers
            )
        self.assertEqual(response.status_code, 200)
        again = await self.client.post("/auth/vk/token", data=params, headers=headers)
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()["error"], "invalid_grant")

    async def test_code_expiry_does_not_contact_vk(self):
        code, _ = await self.code()
        self.store.now += oauth.CODE_TTL
        with patch.object(oauth.httpx, "AsyncClient") as client:
            response = await self.client.post(
                "/auth/vk/token", data=self.token_params(code)
            )
        self.assertEqual(response.status_code, 400)
        client.assert_not_called()

    async def test_concurrent_exchange_can_only_use_code_once(self):
        code, state = await self.code()
        with patch.object(
            oauth.httpx, "AsyncClient", return_value=self.upstream(state)
        ):
            responses = await asyncio.gather(
                *(
                    self.client.post("/auth/vk/token", data=self.token_params(code))
                    for _ in range(2)
                )
            )
        self.assertEqual(sorted(r.status_code for r in responses), [200, 400])
        self.assertEqual(len(self.requests), 2)

    async def test_invalid_configuration_never_redirects(self):
        for field, value in (
            ("vk_oauth_client_id", ""),
            ("vk_oauth_callback_url", "http://api.example.test/callback"),
            (
                "vk_oauth_callback_url",
                "https://user:password@api.example.test/callback",
            ),
            ("vk_oauth_callback_url", "https://[malformed/callback"),
            ("vk_oauth_supabase_callback_url", SUPABASE_CALLBACK + "?untrusted=1"),
        ):
            with patch.object(settings, field, value):
                response = await self.client.get(
                    "/auth/vk/authorize", params=self.auth_params()
                )
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("location", response.headers)

    async def test_profile_and_token_state_must_match_authorization(self):
        for extra in ({"subject": "43"}, {"token_state": "other-state"}):
            code, state = await self.code()
            with patch.object(
                oauth.httpx, "AsyncClient", return_value=self.upstream(state, **extra)
            ):
                response = await self.client.post(
                    "/auth/vk/token", data=self.token_params(code)
                )
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("private-vk-token", response.text)
            self.assertFalse(any(":token:" in k for k in self.store.values))

    async def test_redis_and_upstream_failures_are_closed_and_redacted(self):
        with patch.object(
            self.store, "set_oauth_json", side_effect=OAuthStateUnavailable
        ):
            response = await self.client.get(
                "/auth/vk/authorize", params=self.auth_params()
            )
        self.assertEqual(response.status_code, 503)
        for upstream in (
            httpx.Response(503, json={"error": "private-token"}),
            httpx.Response(200, text="private-token"),
            httpx.ReadTimeout("private-token"),
        ):
            code, _ = await self.code()

            def handler(request):
                if isinstance(upstream, Exception):
                    raise upstream
                return upstream

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            with patch.object(oauth.httpx, "AsyncClient", return_value=client):
                response = await self.client.post(
                    "/auth/vk/token", data=self.token_params(code)
                )
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("private-token", response.text)

    async def test_disabled_provider_and_invalid_requests(self):
        with patch.object(settings, "vk_oauth_bridge_secret", SecretStr("")):
            response = await self.client.get(
                "/auth/vk/authorize", params=self.auth_params()
            )
        self.assertEqual(response.status_code, 503)
        response = await self.client.get("/auth/vk/authorize?client_id=x&client_id=y")
        self.assertEqual(response.status_code, 400)
        response = await self.client.post("/auth/vk/token", json={"code": "secret"})
        self.assertEqual(response.status_code, 415)
        response = await self.client.post(
            "/auth/vk/token",
            content="a=" + "x" * 8192,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(response.status_code, 413)
        for header in ("", "Basic eA==", "Bearer anything"):
            response = await self.client.post(
                "/auth/vk/token",
                data={"grant_type": "authorization_code"},
                headers={"Authorization": header},
            )
            self.assertEqual(response.status_code, 401)
        for header in ("", "Bearer vk-real-access-token", "Basic private-token"):
            response = await self.client.get(
                "/auth/vk/userinfo", headers={"Authorization": header}
            )
            self.assertEqual(response.status_code, 401)
