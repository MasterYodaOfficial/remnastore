from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
import uuid

from app.core.config import settings
from app.integrations.remnawave.client import (
    RemnawaveConfigurationError,
    RemnawaveGateway,
    build_remnawave_description,
    build_remnawave_username,
)


async def _async_none(*args, **kwargs):
    del args, kwargs
    return None


async def _async_empty_list(*args, **kwargs):
    del args, kwargs
    return []


class _FakeUsersController:
    def __init__(self) -> None:
        self.created_bodies = []
        self.updated_bodies = []
        self.client = _FakeUsersHttpClient()

    async def create_user(self, body):
        self.created_bodies.append(body)
        return SimpleNamespace(
            uuid=body.uuid,
            username=body.username,
            status=body.status,
            expire_at=body.expire_at,
            subscription_url="https://panel.test/sub/test-user",
            telegram_id=body.telegram_id,
            email=body.email,
            tag=body.tag,
            hwid_device_limit=body.hwid_device_limit,
        )

    async def update_user(self, body):
        self.updated_bodies.append(body)
        return SimpleNamespace(
            uuid=body.uuid,
            username=body.username or "updated-user",
            status=body.status,
            expire_at=body.expire_at,
            subscription_url="https://panel.test/sub/test-user",
            telegram_id=body.telegram_id,
            email=body.email,
            tag=body.tag,
            hwid_device_limit=body.hwid_device_limit,
        )


class _FakeInternalSquadsController:
    def __init__(self, squads) -> None:
        self._squads = squads

    async def get_internal_squads(self):
        return SimpleNamespace(internal_squads=self._squads)


class _FakeUsersHttpResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeUsersHttpClient:
    def __init__(self) -> None:
        self.patch_calls: list[dict] = []

    async def patch(self, url: str, *, json: dict):
        self.patch_calls.append({"url": url, "json": json})
        payload = {
            "uuid": json["uuid"],
            "id": 1,
            "shortUuid": "shortuuid",
            "username": "updated-user",
            "status": json["status"],
            "trafficLimitBytes": 0,
            "trafficLimitStrategy": "NO_RESET",
            "expireAt": json["expireAt"],
            "telegramId": json.get("telegramId"),
            "email": json.get("email"),
            "description": json.get("description"),
            "tag": json.get("tag"),
            "hwidDeviceLimit": json.get("hwidDeviceLimit"),
            "externalSquadUuid": None,
            "trojanPassword": "password123",
            "vlessUuid": json["uuid"],
            "ssPassword": "password123",
            "lastTriggeredThreshold": 0,
            "subRevokedAt": None,
            "subLastUserAgent": None,
            "subLastOpenedAt": None,
            "lastTrafficResetAt": None,
            "createdAt": "2026-03-16T00:00:00Z",
            "updatedAt": "2026-03-16T00:00:00Z",
            "subscriptionUrl": "https://panel.test/sub/test-user",
            "activeInternalSquads": [],
            "userTraffic": {
                "usedTrafficBytes": 0,
                "lifetimeUsedTrafficBytes": 0,
                "onlineAt": None,
                "firstConnectedAt": None,
                "lastConnectedNodeUuid": None,
            },
        }
        return _FakeUsersHttpResponse(payload)


class RemnawaveClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._original_username_prefix = settings.remnawave_username_prefix
        self._original_user_label = settings.remnawave_user_label
        self._original_bot_username = settings.telegram_bot_username
        self._original_default_squad_uuid = settings.remnawave_default_internal_squad_uuid
        self._original_default_squad_name = settings.remnawave_default_internal_squad_name

    def tearDown(self) -> None:
        settings.remnawave_username_prefix = self._original_username_prefix
        settings.remnawave_user_label = self._original_user_label
        settings.telegram_bot_username = self._original_bot_username
        settings.remnawave_default_internal_squad_uuid = self._original_default_squad_uuid
        settings.remnawave_default_internal_squad_name = self._original_default_squad_name

    def _make_gateway(self, *, squads) -> RemnawaveGateway:
        gateway = object.__new__(RemnawaveGateway)
        gateway._sdk = SimpleNamespace(
            users=_FakeUsersController(),
            internal_squads=_FakeInternalSquadsController(squads),
        )
        gateway._default_internal_squad_uuid_cache = None
        gateway._default_internal_squad_uuid_resolved = False
        gateway.get_user_by_uuid = _async_none
        gateway.get_user_by_username = _async_none
        gateway.get_users_by_email = _async_empty_list
        gateway.get_users_by_telegram_id = _async_empty_list
        return gateway

    def test_build_remnawave_username_uses_configured_prefix_and_telegram_id(self) -> None:
        settings.remnawave_username_prefix = "Logo VPN"
        user_uuid = uuid.UUID("11111111-1111-1111-1111-111111111111")

        username = build_remnawave_username(user_uuid, telegram_id=123456789)

        self.assertEqual(username, "logo_vpn_tg123456789")

    def test_build_remnawave_description_uses_label_and_trial_marker(self) -> None:
        settings.remnawave_user_label = "Remna Store"
        user_uuid = uuid.UUID("22222222-2222-2222-2222-222222222222")

        description = build_remnawave_description(
            user_uuid=user_uuid,
            telegram_id=777001,
            is_trial=True,
        )

        self.assertEqual(
            description,
            "Remna Store | tg:777001 | trial | uuid:22222222-2222-2222-2222-222222222222",
        )

    async def test_provision_user_assigns_single_available_internal_squad(self) -> None:
        settings.remnawave_username_prefix = "remna"
        settings.remnawave_user_label = "RemnaStore"
        settings.remnawave_default_internal_squad_uuid = ""
        settings.remnawave_default_internal_squad_name = ""
        squad_uuid = uuid.UUID("33333333-3333-3333-3333-333333333333")
        gateway = self._make_gateway(
            squads=[SimpleNamespace(uuid=squad_uuid, name="Default Squad")]
        )

        user = await gateway.provision_user(
            user_uuid=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            expire_at=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
            email="user@example.com",
            telegram_id=700001,
            is_trial=False,
            hwid_device_limit=3,
        )

        body = gateway._sdk.users.created_bodies[0]
        self.assertEqual(body.username, "remna_tg700001")
        self.assertEqual(body.active_internal_squads, [squad_uuid])
        self.assertEqual(
            body.description,
            "RemnaStore | tg:700001 | uuid:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        )
        self.assertEqual(user.username, "remna_tg700001")

    async def test_provision_user_resolves_internal_squad_by_configured_name(self) -> None:
        settings.remnawave_default_internal_squad_uuid = ""
        settings.remnawave_default_internal_squad_name = "VIP"
        default_uuid = uuid.UUID("44444444-4444-4444-4444-444444444444")
        vip_uuid = uuid.UUID("55555555-5555-5555-5555-555555555555")
        gateway = self._make_gateway(
            squads=[
                SimpleNamespace(uuid=default_uuid, name="DEFAULT"),
                SimpleNamespace(uuid=vip_uuid, name="VIP"),
            ]
        )

        await gateway.provision_user(
            user_uuid=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            expire_at=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
            email=None,
            telegram_id=700002,
            is_trial=True,
            hwid_device_limit=None,
        )

        body = gateway._sdk.users.created_bodies[0]
        self.assertEqual(body.active_internal_squads, [vip_uuid])

    async def test_provision_user_requires_explicit_config_when_multiple_squads_exist(self) -> None:
        settings.remnawave_default_internal_squad_uuid = ""
        settings.remnawave_default_internal_squad_name = ""
        gateway = self._make_gateway(
            squads=[
                SimpleNamespace(uuid=uuid.uuid4(), name="DEFAULT"),
                SimpleNamespace(uuid=uuid.uuid4(), name="VIP"),
            ]
        )

        with self.assertRaisesRegex(
            RemnawaveConfigurationError,
            "Multiple Remnawave internal squads found",
        ):
            await gateway.provision_user(
                user_uuid=uuid.uuid4(),
                expire_at=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
                email=None,
                telegram_id=700003,
                is_trial=False,
                hwid_device_limit=None,
            )

    async def test_provision_user_clears_trial_tag_via_raw_patch(self) -> None:
        settings.remnawave_default_internal_squad_uuid = ""
        settings.remnawave_default_internal_squad_name = ""
        squad_uuid = uuid.UUID("66666666-6666-6666-6666-666666666666")
        gateway = self._make_gateway(
            squads=[SimpleNamespace(uuid=squad_uuid, name="DEFAULT")]
        )
        existing_uuid = uuid.UUID("77777777-7777-7777-7777-777777777777")

        async def _existing_trial_user(user_uuid):
            del user_uuid
            return SimpleNamespace(
                uuid=existing_uuid,
                username="existing-user",
                status="ACTIVE",
                expire_at=datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
                subscription_url="https://panel.test/sub/existing",
                telegram_id=700004,
                email="trial@example.com",
                tag="TRIAL",
                hwid_device_limit=3,
            )

        gateway.get_user_by_uuid = _existing_trial_user

        await gateway.provision_user(
            user_uuid=existing_uuid,
            expire_at=datetime(2026, 4, 18, 12, 0, tzinfo=UTC),
            email="trial@example.com",
            telegram_id=700004,
            is_trial=False,
            hwid_device_limit=3,
        )

        patch_call = gateway._sdk.users.client.patch_calls[0]
        self.assertEqual(patch_call["url"], "users")
        self.assertIn("tag", patch_call["json"])
        self.assertIsNone(patch_call["json"]["tag"])

    async def test_provision_user_reuses_existing_remote_user_found_by_username(self) -> None:
        settings.remnawave_username_prefix = "acc"
        squad_uuid = uuid.UUID("88888888-8888-8888-8888-888888888888")
        gateway = self._make_gateway(
            squads=[SimpleNamespace(uuid=squad_uuid, name="DEFAULT")]
        )
        requested_uuid = uuid.UUID("99999999-9999-9999-9999-999999999999")
        existing_uuid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        async def _existing_by_username(username):
            self.assertEqual(username, "acc_tg700005")
            return SimpleNamespace(
                uuid=existing_uuid,
                username=username,
                status="ACTIVE",
                expire_at=datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
                subscription_url="https://panel.test/sub/existing-username",
                telegram_id=700005,
                email="existing-username@example.com",
                tag=None,
                hwid_device_limit=3,
            )

        gateway.get_user_by_username = _existing_by_username

        user = await gateway.provision_user(
            user_uuid=requested_uuid,
            expire_at=datetime(2026, 4, 18, 12, 0, tzinfo=UTC),
            email="existing-username@example.com",
            telegram_id=700005,
            is_trial=False,
            hwid_device_limit=3,
        )

        self.assertEqual(gateway._sdk.users.created_bodies, [])
        self.assertEqual(len(gateway._sdk.users.updated_bodies), 1)
        self.assertEqual(gateway._sdk.users.updated_bodies[0].uuid, existing_uuid)
        self.assertEqual(user.uuid, existing_uuid)

    async def test_provision_user_reuses_unique_remote_user_found_by_telegram_id(self) -> None:
        settings.remnawave_username_prefix = "acc"
        squad_uuid = uuid.UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
        gateway = self._make_gateway(
            squads=[SimpleNamespace(uuid=squad_uuid, name="DEFAULT")]
        )
        requested_uuid = uuid.UUID("12121212-3434-5656-7878-909090909090")
        existing_uuid = uuid.UUID("13131313-3535-5757-7979-919191919191")

        async def _existing_by_telegram(telegram_id):
            self.assertEqual(telegram_id, 700006)
            return [
                SimpleNamespace(
                    uuid=existing_uuid,
                    username="legacy_prefix_tg700006",
                    status="ACTIVE",
                    expire_at=datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
                    subscription_url="https://panel.test/sub/existing-telegram",
                    telegram_id=700006,
                    email="existing-telegram@example.com",
                    tag=None,
                    hwid_device_limit=2,
                )
            ]

        gateway.get_users_by_telegram_id = _existing_by_telegram

        user = await gateway.provision_user(
            user_uuid=requested_uuid,
            expire_at=datetime(2026, 4, 18, 12, 0, tzinfo=UTC),
            email="existing-telegram@example.com",
            telegram_id=700006,
            is_trial=False,
            hwid_device_limit=2,
        )

        self.assertEqual(gateway._sdk.users.created_bodies, [])
        self.assertEqual(len(gateway._sdk.users.updated_bodies), 1)
        self.assertEqual(gateway._sdk.users.updated_bodies[0].uuid, existing_uuid)
        self.assertEqual(user.uuid, existing_uuid)


if __name__ == "__main__":
    unittest.main()
