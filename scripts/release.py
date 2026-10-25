"""Validate release inputs and publish a complete, reviewed release from CI.

No third-party Python dependencies are required. Publication needs Docker/Buildx,
GH_TOKEN and a successful CI job for the current main commit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

COMPONENTS = ("api", "bot", "web", "admin")
VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
ROOT = Path(__file__).resolve().parents[1]


class ReleaseError(RuntimeError):
    pass


def version_key(value: str) -> tuple[int, int, int]:
    if not VERSION_PATTERN.fullmatch(value):
        raise ReleaseError("VERSION должен содержать стабильный номер X.Y.Z без v.")
    return tuple(map(int, value.split(".")))


@dataclass(frozen=True)
class Release:
    version: str
    title: str
    body: str


def read_release(root: Path = ROOT) -> Release:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    version_key(version)
    notes = root / "releases" / f"{version}.md"
    if not notes.is_file():
        raise ReleaseError(f"Не найдено описание releases/{version}.md.")
    lines = notes.read_text(encoding="utf-8").strip().splitlines()
    if not lines or lines[0] != f"# RemnaStore {version}":
        raise ReleaseError("Первая строка описания должна быть # RemnaStore <версия>.")
    body = "\n".join(lines[1:]).strip()
    if not re.search("[А-Яа-яЁё]", body):
        raise ReleaseError("Описание выпуска должно содержать русский текст.")
    return Release(version, lines[0][2:], body + "\n")


def command(*args: str, cwd: Path = ROOT, check: bool = True):
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode:
        raise ReleaseError(
            f"Команда {args[0]} завершилась с ошибкой: {result.stderr.strip()}"
        )
    return result


def validate_history(
    release: Release, *, root: Path, base_ref: str | None, publish: bool
):
    if base_ref:
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", base_ref) or base_ref.startswith("-"):
            raise ReleaseError("Недопустимая базовая ветка.")
        previous = command("git", "show", f"{base_ref}:VERSION", cwd=root, check=False)
        if previous.returncode == 0 and version_key(release.version) <= version_key(
            previous.stdout.strip()
        ):
            raise ReleaseError("Для PR в main увеличьте VERSION относительно main.")
    tags = command("git", "tag", "--list", "v*", cwd=root).stdout.splitlines()
    versions = [tag[1:] for tag in tags if VERSION_PATTERN.fullmatch(tag[1:])]
    if (base_ref or publish) and any(
        version_key(v) > version_key(release.version) for v in versions
    ):
        raise ReleaseError("Номер выпуска меньше уже существующего тега.")
    if base_ref and f"v{release.version}" in tags:
        raise ReleaseError("Этот номер уже занят тегом; выберите следующий.")
    if publish and f"v{release.version}" in tags:
        tagged = command(
            "git", "rev-parse", f"v{release.version}^{{commit}}", cwd=root
        ).stdout.strip()
        if tagged != os.environ.get("GITHUB_SHA"):
            raise ReleaseError("Номер выпуска уже принадлежит другому коммиту.")


class GitHub:
    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ReleaseError("Недопустимый GitHub repository.")
        self.repository, self.token = repository, token

    def request(self, path: str, *, method="GET", payload=None, missing_ok=False):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        return self._request(
            "https://api.github.com/repos/" + self.repository + path,
            method,
            data,
            "application/json",
            missing_ok,
        )

    def _request(self, url, method, data, content_type, missing_ok=False):
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": content_type,
                "User-Agent": "remnastore-release",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response) if response.status != 204 else None
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise ReleaseError(f"GitHub API: HTTP {exc.code} ({method}).") from exc

    def upload(self, release_id: int, name: str, data: bytes):
        url = f"https://uploads.github.com/repos/{self.repository}/releases/{release_id}/assets?{urlencode({'name': name})}"
        return self._request(url, "POST", data, "application/octet-stream")


def missing_manifest(result) -> bool:
    return result.returncode != 0 and any(
        message in result.stderr.lower()
        for message in (
            "manifest unknown",
            "no such manifest",
            "not found",
        )
    )


def remote_digest(image: str) -> str | None:
    result = command("docker", "buildx", "imagetools", "inspect", image, check=False)
    if missing_manifest(result):
        return None
    if result.returncode:
        raise ReleaseError(
            f"Не удалось проверить образ {image}: {result.stderr.strip()}"
        )
    match = re.search(
        r"^Digest:\s+(sha256:[0-9a-f]{64})\s*$", result.stdout, re.MULTILINE
    )
    if not match:
        raise ReleaseError(f"Не найден digest образа {image}.")
    return match.group(1)


def check_image_labels(image: str, release: Release, sha: str):
    labels = (
        json.loads(
            command(
                "docker",
                "image",
                "inspect",
                "--format",
                "{{json .Config.Labels}}",
                image,
            ).stdout
        )
        or {}
    )
    if (
        labels.get("org.opencontainers.image.version") != release.version
        or labels.get("org.opencontainers.image.revision") != sha
    ):
        raise ReleaseError(
            f"Образ {image} принадлежит другой версии или коммиту; перезапись запрещена."
        )


def ensure_current(github: GitHub, release: Release, sha: str):
    if github.request("/git/ref/heads/main")["object"]["sha"] != sha:
        raise ReleaseError("main уже обновлён: этот запуск не может менять latest.")
    latest = github.request("/releases/latest", missing_ok=True)
    if latest and VERSION_PATTERN.fullmatch(latest["tag_name"].removeprefix("v")):
        if version_key(latest["tag_name"].removeprefix("v")) > version_key(
            release.version
        ):
            raise ReleaseError("Более новый выпуск уже опубликован; latest не изменён.")


def promote(image_repository: str, component: str, digest: str):
    if not DIGEST_PATTERN.fullmatch(digest):
        raise ReleaseError("Недопустимый digest.")
    command(
        "docker",
        "buildx",
        "imagetools",
        "create",
        "--prefer-index=false",
        "--tag",
        f"{image_repository}:{component}-latest",
        f"{image_repository}@{digest}",
    )


def publish_release(
    release: Release,
    *,
    root: Path,
    artifacts: Path,
    repository: str,
    sha: str,
    github: GitHub,
):
    if not SHA_PATTERN.fullmatch(sha):
        raise ReleaseError("Не задан полный SHA коммита.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*", repository):
        raise ReleaseError("Недопустимый Docker Hub repository.")
    ensure_current(github, release, sha)
    existing = github.request(f"/releases/tags/v{release.version}", missing_ok=True)
    if existing and not existing["draft"]:
        if github.request(f"/commits/v{release.version}")["sha"] != sha:
            raise ReleaseError("Выпуск уже опубликован из другого коммита.")
        print(f"v{release.version} уже опубликован; повторная публикация не требуется.")
        return
    if existing and existing["target_commitish"] != sha:
        raise ReleaseError("Черновик выпуска принадлежит другому коммиту.")

    digests, previous_latest, pending = {}, {}, []
    # Check every existing numbered tag before pushing anything.
    for component in COMPONENTS:
        image = f"{repository}:{component}-{release.version}"
        digest = remote_digest(image)
        if digest:
            command("docker", "pull", "--quiet", image)
            check_image_labels(image, release, sha)
            digests[component] = digest
        else:
            path = artifacts / f"{component}.tar"
            if not path.is_file():
                raise ReleaseError(f"Не найден собранный образ {path.name}.")
            command("docker", "load", "--input", str(path))
            staging = f"{repository}:{component}-{sha[:12]}"
            check_image_labels(staging, release, sha)
            pending.append((component, staging, image))
        previous_latest[component] = remote_digest(f"{repository}:{component}-latest")

    for component, staging, image in pending:
        command("docker", "tag", staging, image)
        command("docker", "push", staging)
        command("docker", "push", image)
        digest = remote_digest(image)
        if digest is None:
            raise ReleaseError(f"Не опубликован номерной образ {image}.")
        digests[component] = digest

    ensure_current(github, release, sha)
    payload = {
        "tag_name": f"v{release.version}",
        "target_commitish": sha,
        "name": release.title,
        "body": release.body,
        "draft": True,
        "prerelease": False,
        "make_latest": "false",
    }
    draft = github.request(
        f"/releases/{existing['id']}" if existing else "/releases",
        method="PATCH" if existing else "POST",
        payload=payload,
    )
    assets = {
        "compose.yml": (root / "deploy/compose.yml").read_bytes(),
        "env.example": (root / "deploy/.env.example").read_bytes(),
        "yandex-id.md": (root / "docs/yandex-id.md").read_bytes(),
        "configure_yandex_auth.py": (
            root / "scripts/configure_yandex_auth.py"
        ).read_bytes(),
        "VERSION": (release.version + "\n").encode(),
        "images.json": json.dumps(
            {
                "version": release.version,
                "revision": sha,
                "repository": repository,
                "images": digests,
            },
            indent=2,
        ).encode(),
    }
    for name, content in assets.items():
        for asset in draft.get("assets", []):
            if asset["name"] == name:
                github.request(f"/releases/assets/{asset['id']}", method="DELETE")
        github.upload(draft["id"], name, content)

    touched = []
    publishing = False
    try:
        ensure_current(github, release, sha)
        for component in COMPONENTS:
            # Include the attempted component: a failed command may have reached Docker Hub.
            touched.append(component)
            promote(repository, component, digests[component])
        ensure_current(github, release, sha)
        publishing = True
        github.request(
            f"/releases/{draft['id']}",
            method="PATCH",
            payload={"draft": False, "make_latest": "true"},
        )
    except Exception:
        if publishing:
            # A lost response can hide a successful publication. Keep the complete
            # image set if GitHub confirms publication or cannot answer the check.
            published = github.request(f"/releases/{draft['id']}")
            if not published["draft"]:
                print(f"Опубликован v{release.version}: {draft['html_url']}")
                return
        for component in reversed(touched):
            if previous_latest[component]:
                try:
                    promote(repository, component, previous_latest[component])
                except Exception as rollback_error:
                    print(
                        f"Не удалось восстановить {component}-latest: {rollback_error}",
                        file=sys.stderr,
                    )
        raise
    print(f"Опубликован v{release.version}: {draft['html_url']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "prepare", "publish"))
    parser.add_argument("--base-ref")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--artifacts", type=Path, default=Path("images"))
    args = parser.parse_args()
    release = read_release()
    validate_history(
        release,
        root=ROOT,
        base_ref=args.base_ref,
        publish=args.publish or args.action == "publish",
    )
    if args.action == "prepare":
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"version={release.version}\n")
    elif args.action == "publish":
        if os.environ.get("GITHUB_REF") != "refs/heads/main" or os.environ.get(
            "GITHUB_EVENT_NAME"
        ) not in ("push", "workflow_dispatch"):
            raise ReleaseError("Публикация разрешена только после CI в main.")
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            raise ReleaseError("Для публикации нужен GH_TOKEN.")
        publish_release(
            release,
            root=ROOT,
            artifacts=args.artifacts,
            repository=os.environ["DOCKERHUB_REPOSITORY"],
            sha=os.environ["GITHUB_SHA"],
            github=GitHub(os.environ["GITHUB_REPOSITORY"], token),
        )
    print(f"Описание и версия {release.version} проверены.")


if __name__ == "__main__":
    try:
        main()
    except (ReleaseError, OSError, ValueError) as error:
        print(f"Ошибка выпуска: {error}", file=sys.stderr)
        raise SystemExit(1) from error
