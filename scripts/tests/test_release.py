import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release as tool

SHA = "a" * 40
REPOSITORY = "example/remnastore"
OLD = {c: "sha256:" + str(i) * 64 for i, c in enumerate(tool.COMPONENTS, 1)}
NEW = {c: "sha256:" + str(i) * 64 for i, c in enumerate(tool.COMPONENTS, 5)}


class FakeGitHub:
    def __init__(self):
        self.main_sha = SHA
        self.latest = None
        self.release = None
        self.uploads = {}
        self.events = []
        self.fail_publish = False
        self.lose_publish_response = False

    def request(self, path, *, method="GET", payload=None, missing_ok=False):
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main_sha}}
        if path == "/releases/latest":
            return self.latest
        if path.startswith("/commits/"):
            return {"sha": SHA}
        if path.startswith("/releases/tags/"):
            return self.release
        if method == "POST" and path == "/releases":
            self.release = {
                "id": 7,
                "assets": [],
                "html_url": "https://github.test/release",
                **payload,
            }
            self.events.append("draft")
            return self.release
        if path == "/releases/7":
            if method == "PATCH":
                if payload.get("draft") is False and self.fail_publish:
                    raise tool.ReleaseError("GitHub unavailable")
                self.release.update(payload)
                self.events.append(
                    "published" if not self.release["draft"] else "draft"
                )
                if payload.get("draft") is False and self.lose_publish_response:
                    raise tool.ReleaseError("Published, but response lost")
            return self.release
        if method == "DELETE" and path.startswith("/releases/assets/"):
            return None
        raise AssertionError((method, path))

    def upload(self, release_id, name, content):
        assert release_id == 7
        self.uploads[name] = content


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "releases").mkdir()
        (self.root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
        (self.root / "releases/1.2.3.md").write_text(
            "# RemnaStore 1.2.3\n\nИсправлены ошибки.\n", encoding="utf-8"
        )
        (self.root / "deploy").mkdir()
        (self.root / "deploy/compose.yml").write_text(
            "services: {}\n", encoding="utf-8"
        )
        (self.root / "deploy/.env.example").write_text(
            "REMNASTORE_VERSION=latest\n", encoding="utf-8"
        )
        self.artifacts = self.root / "images"
        self.artifacts.mkdir()
        for component in tool.COMPONENTS:
            (self.artifacts / f"{component}.tar").write_bytes(b"image artifact")
        self.release = tool.read_release(self.root)
        self.github = FakeGitHub()
        self.remote = {f"{REPOSITORY}:{c}-latest": digest for c, digest in OLD.items()}
        self.calls = []
        self.bad_labels = set()
        self.fail_promotion = None
        self.failed_promotion = False
        self.fail_push = False
        self.move_main_after_push = False

    def command(self, *args, **kwargs):
        self.calls.append(args)
        if args[:3] == ("docker", "image", "inspect"):
            labels = {
                "org.opencontainers.image.version": self.release.version,
                "org.opencontainers.image.revision": "b" * 40
                if args[-1] in self.bad_labels
                else SHA,
            }
            return subprocess.CompletedProcess(args, 0, json.dumps(labels), "")
        if args[:2] == ("docker", "push"):
            if self.fail_push:
                raise tool.ReleaseError("Registry unavailable")
            component = args[-1].split(":")[1].split("-")[0]
            self.remote[args[-1]] = NEW[component]
            if self.move_main_after_push:
                self.github.main_sha = "b" * 40
        if args[:4] == ("docker", "buildx", "imagetools", "create"):
            image, digest = args[-2], args[-1].split("@")[1]
            # A request can take effect remotely and then lose its response.
            self.remote[image] = digest
            component = image.split(":")[1].split("-")[0]
            if component == self.fail_promotion and not self.failed_promotion:
                self.failed_promotion = True
                raise tool.ReleaseError("Connection lost")
        return subprocess.CompletedProcess(args, 0, "", "")

    def publish(self):
        with (
            patch.object(tool, "command", side_effect=self.command),
            patch.object(
                tool, "remote_digest", side_effect=lambda name: self.remote.get(name)
            ),
        ):
            tool.publish_release(
                self.release,
                root=self.root,
                artifacts=self.artifacts,
                repository=REPOSITORY,
                sha=SHA,
                github=self.github,
            )

    def assert_latest_unchanged(self):
        for component, digest in OLD.items():
            self.assertEqual(self.remote[f"{REPOSITORY}:{component}-latest"], digest)

    def test_lost_publication_response_keeps_published_images(self):
        self.github.lose_publish_response = True
        self.publish()
        self.assertFalse(self.github.release["draft"])
        for component, digest in NEW.items():
            self.assertEqual(self.remote[f"{REPOSITORY}:{component}-latest"], digest)

    def test_reviewed_russian_notes_are_used_verbatim(self):
        self.publish()
        self.assertEqual(self.github.release["body"], "Исправлены ошибки.\n")
        self.assertEqual(self.github.release["target_commitish"], SHA)
        self.assertFalse(self.github.release["draft"])
        self.assertEqual(self.github.events, ["draft", "published"])
        self.assertEqual(
            set(self.github.uploads),
            {"compose.yml", "env.example", "VERSION", "images.json"},
        )
        self.assertEqual(json.loads(self.github.uploads["images.json"])["images"], NEW)
        first_promotion = next(
            i for i, call in enumerate(self.calls) if "create" in call
        )
        self.assertEqual(
            sum(
                call[:2] == ("docker", "push") for call in self.calls[:first_promotion]
            ),
            8,
        )

    def test_missing_image_artifact_prevents_all_pushes(self):
        (self.artifacts / "admin.tar").unlink()
        with self.assertRaises(tool.ReleaseError):
            self.publish()
        self.assertFalse(any(call[:2] == ("docker", "push") for call in self.calls))
        self.assert_latest_unchanged()

    def test_existing_version_from_another_commit_is_not_overwritten(self):
        image = f"{REPOSITORY}:api-1.2.3"
        self.remote[image] = NEW["api"]
        self.bad_labels.add(image)
        with self.assertRaises(tool.ReleaseError):
            self.publish()
        self.assertFalse(any(call[:2] == ("docker", "push") for call in self.calls))
        self.assert_latest_unchanged()

    def test_partial_retry_reuses_numbered_image_without_republishing_it(self):
        image = f"{REPOSITORY}:api-1.2.3"
        self.remote[image] = NEW["api"]
        (self.artifacts / "api.tar").unlink()
        self.publish()
        self.assertNotIn(("docker", "push", image), self.calls)
        self.assertFalse(self.github.release["draft"])

    def test_failure_while_pushing_leaves_latest_unchanged(self):
        self.fail_push = True
        with self.assertRaises(tool.ReleaseError):
            self.publish()
        self.assert_latest_unchanged()
        self.assertIsNone(self.github.release)

    def test_partial_latest_failure_restores_previous_release(self):
        self.fail_promotion = "web"
        with self.assertRaises(tool.ReleaseError):
            self.publish()
        self.assert_latest_unchanged()
        self.assertTrue(self.github.release["draft"])

    def test_failed_github_publication_restores_latest_and_can_retry(self):
        self.github.fail_publish = True
        with self.assertRaises(tool.ReleaseError):
            self.publish()
        self.assert_latest_unchanged()
        self.github.fail_publish = False
        self.publish()
        self.assertFalse(self.github.release["draft"])

    def test_completed_publication_is_idempotent(self):
        self.publish()
        self.calls.clear()
        self.publish()
        self.assertEqual(self.calls, [])

    def test_stale_main_run_cannot_publish(self):
        self.github.main_sha = "b" * 40
        with self.assertRaises(tool.ReleaseError):
            self.publish()
        self.assertEqual(self.calls, [])
        self.assert_latest_unchanged()

    def test_main_moving_during_push_prevents_latest_update(self):
        self.move_main_after_push = True
        with self.assertRaises(tool.ReleaseError):
            self.publish()
        self.assert_latest_unchanged()
        self.assertIsNone(self.github.release)

    def test_newer_published_release_cannot_be_replaced(self):
        self.github.latest = {"tag_name": "v2.0.0"}
        with self.assertRaises(tool.ReleaseError):
            self.publish()
        self.assertEqual(self.calls, [])

    def test_version_rejects_path_traversal_and_nonstable_names(self):
        for value in ("../secret", "01.2.3", "v1.2.3", "1.2.3-rc.1", "1.2"):
            with self.subTest(value=value), self.assertRaises(tool.ReleaseError):
                tool.version_key(value)

    def test_russian_notes_are_required(self):
        (self.root / "releases/1.2.3.md").write_text(
            "# RemnaStore 1.2.3\nEnglish only", encoding="utf-8"
        )
        with self.assertRaises(tool.ReleaseError):
            tool.read_release(self.root)

    def test_main_release_pr_requires_version_bump(self):
        result = subprocess.CompletedProcess([], 0, "1.2.3", "")
        with (
            patch.object(tool, "command", return_value=result),
            self.assertRaises(tool.ReleaseError),
        ):
            tool.validate_history(
                self.release, root=self.root, base_ref="origin/main", publish=False
            )

    def test_manual_retry_cannot_reuse_tag_of_another_commit(self):
        with (
            patch.object(
                tool,
                "command",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "v1.2.3\n", ""),
                    subprocess.CompletedProcess([], 0, "b" * 40, ""),
                ],
            ),
            patch.dict(os.environ, {"GITHUB_SHA": SHA}),
            self.assertRaises(tool.ReleaseError),
        ):
            tool.validate_history(
                self.release, root=self.root, base_ref=None, publish=True
            )

    def test_manifest_network_error_is_not_treated_as_missing_image(self):
        with (
            patch.object(
                tool,
                "command",
                return_value=subprocess.CompletedProcess(
                    [], 1, "", "connection timed out"
                ),
            ),
            self.assertRaises(tool.ReleaseError),
        ):
            tool.remote_digest("example/repo:api-1.2.3")

    def test_existing_digest_and_missing_manifest_are_distinguished(self):
        with patch.object(
            tool,
            "command",
            return_value=subprocess.CompletedProcess(
                [], 0, f"Name: example/repo\nDigest: {OLD['api']}\n", ""
            ),
        ):
            self.assertEqual(tool.remote_digest("example/repo:tag"), OLD["api"])
        with patch.object(
            tool,
            "command",
            return_value=subprocess.CompletedProcess([], 1, "", "manifest unknown"),
        ):
            self.assertIsNone(tool.remote_digest("example/repo:tag"))
