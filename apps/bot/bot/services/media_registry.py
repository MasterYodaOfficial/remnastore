from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from aiogram.types import FSInputFile, InputFile, Message
from redis.asyncio import Redis

from bot.core.config import settings


def _build_redis_client() -> Redis | None:
    redis_url = settings.redis_url.strip()
    if not redis_url:
        return None
    return Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)


_redis_client: Redis | None = _build_redis_client()
_memory_media_ids: dict[str, str] = {}


@dataclass(frozen=True, slots=True)
class MediaAsset:
    name: str
    path: Path
    asset_hash: str


class MediaRegistry:
    def __init__(self) -> None:
        self._assets_dir = self._resolve_assets_dir()

    @staticmethod
    def _resolve_assets_dir() -> Path:
        if settings.bot_assets_dir.strip():
            return Path(settings.bot_assets_dir.strip()).resolve()

        here = Path(__file__).resolve()
        return (here.parents[1] / "assets" / "menu").resolve()

    @lru_cache(maxsize=8)
    def get_asset(self, asset_name: str) -> MediaAsset:
        for extension in ("jpg", "jpeg", "png"):
            candidate = self._assets_dir / f"{asset_name}.{extension}"
            if not candidate.exists():
                continue
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()[:8]
            return MediaAsset(name=asset_name, path=candidate, asset_hash=digest)
        raise RuntimeError(f"Asset not found for {asset_name!r} in {self._assets_dir}")

    @staticmethod
    def _cache_key(asset: MediaAsset) -> str:
        return f"bot:menu:v1:media:{asset.name}:{asset.asset_hash}"

    async def get_input_file(self, asset_name: str) -> str | InputFile:
        asset = self.get_asset(asset_name)
        if _redis_client is not None:
            cached_file_id = await _redis_client.get(self._cache_key(asset))
        else:
            cached_file_id = _memory_media_ids.get(self._cache_key(asset))

        if cached_file_id:
            return cached_file_id

        return FSInputFile(asset.path)

    async def remember_message_media(self, asset_name: str, message: Message | None) -> None:
        if message is None or not message.photo:
            return

        file_id = message.photo[-1].file_id
        asset = self.get_asset(asset_name)
        if _redis_client is not None:
            await _redis_client.set(self._cache_key(asset), file_id)
            return

        _memory_media_ids[self._cache_key(asset)] = file_id

    async def close(self) -> None:
        if _redis_client is not None:
            await _redis_client.aclose()


_media_registry = MediaRegistry()


def get_media_registry() -> MediaRegistry:
    return _media_registry
