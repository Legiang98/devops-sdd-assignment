import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from devops.observability.evaluation import resolve_deployment_state as resolver


class ResolveDeploymentStateTests(unittest.TestCase):
    def test_resolve_prefers_state_file_for_last_known_healthy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "devops" / "k8s" / "sample-app").mkdir(parents=True)
            (root / "devops" / "state").mkdir(parents=True)

            image_tag = root / "devops" / "k8s" / "sample-app" / "image-tag.yaml"
            image_tag.write_text(
                "# Auto-updated by CI pipeline.\nimage:\n  repository: sample-app\n  tag: current123\n",
                encoding="utf-8",
            )
            (root / "devops" / "state" / "sample-app.json").write_text(
                json.dumps(
                    {
                        "last_known_healthy": {
                            "repository": "sample-app",
                            "tag": "healthy456",
                            "version": "sample-app:healthy456",
                        }
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(resolver, "ROOT", root), mock.patch.object(
                resolver, "K8S_ROOT", root / "devops" / "k8s"
            ), mock.patch.object(resolver, "STATE_ROOT", root / "devops" / "state"), mock.patch.object(
                resolver, "read_previous_image", return_value=None
            ):
                payload = resolver.resolve_state("sample-app")

            self.assertEqual(payload["current"]["version"], "sample-app:current123")
            self.assertEqual(payload["last_known_healthy"]["version"], "sample-app:healthy456")
            self.assertEqual(payload["last_known_healthy_source"], "state_file")

    def test_resolve_falls_back_to_previous_version_when_state_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "devops" / "k8s" / "sample-app").mkdir(parents=True)
            image_tag = root / "devops" / "k8s" / "sample-app" / "image-tag.yaml"
            image_tag.write_text(
                "# Auto-updated by CI pipeline.\nimage:\n  repository: sample-app\n  tag: current123\n",
                encoding="utf-8",
            )
            previous = {
                "repository": "sample-app",
                "tag": "prev999",
                "version": "sample-app:prev999",
                "git_commit": "abc123",
            }

            with mock.patch.object(resolver, "ROOT", root), mock.patch.object(
                resolver, "K8S_ROOT", root / "devops" / "k8s"
            ), mock.patch.object(resolver, "STATE_ROOT", root / "devops" / "state"), mock.patch.object(
                resolver, "read_previous_image", return_value=previous
            ):
                payload = resolver.resolve_state("sample-app")

            self.assertEqual(payload["last_known_healthy"]["version"], "sample-app:prev999")
            self.assertEqual(payload["last_known_healthy_source"], "previous_version_fallback")

    def test_promote_writes_state_file_from_current_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "devops" / "k8s" / "sample-app").mkdir(parents=True)
            (root / "devops" / "state").mkdir(parents=True)
            (root / "devops" / "k8s" / "sample-app" / "image-tag.yaml").write_text(
                "# Auto-updated by CI pipeline.\nimage:\n  repository: sample-app\n  tag: current123\n",
                encoding="utf-8",
            )

            with mock.patch.object(resolver, "ROOT", root), mock.patch.object(
                resolver, "K8S_ROOT", root / "devops" / "k8s"
            ), mock.patch.object(resolver, "STATE_ROOT", root / "devops" / "state"):
                payload = resolver.promote_state(
                    "sample-app",
                    change_id="deploy-1",
                    git_sha="deadbeef",
                    workflow_run_id="42",
                    source="observability",
                )

            self.assertEqual(payload["last_known_healthy"]["version"], "sample-app:current123")
            stored = json.loads((root / "devops" / "state" / "sample-app.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["current_candidate"]["change_id"], "deploy-1")


if __name__ == "__main__":
    unittest.main()
