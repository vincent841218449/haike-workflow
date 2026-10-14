"""Migration checks use isolated configuration, never live credentials or services."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PORTABLE = Path(__file__).resolve().parents[1] / "portable"
sys.path.insert(0, str(PORTABLE))
spec = importlib.util.spec_from_file_location("macos_launcher", PORTABLE / "macos.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class MacosMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(launcher, "ROOT", self.root).start()
        for repo in launcher.bundle.REPOS:
            python = self.root / repo / ".venv/bin/python"
            python.parent.mkdir(parents=True)
            python.touch()
        for rel in ("Haike_video/.env.example", "creatorhub/config.example.yaml"):
            (self.root / rel).write_text("# example\n")
        self.default = self.root / "copy_skill/copy_skill-main/config/content_intelligence.json"
        self.default.parent.mkdir(parents=True)
        self.default.write_text(json.dumps({"media_tools": {"ffmpeg": "original"}, "jobs": {}}))
        self.local = self.default.with_name("content_intelligence.local.json")

    def test_prepare_preserves_public_config_and_existing_local_values(self):
        original = self.default.read_bytes()
        self.local.write_text(json.dumps({"local_marker": "preserved", "jobs": {}}))
        launcher.prepare()
        self.assertEqual(self.default.read_bytes(), original)
        data = json.loads(self.local.read_text())
        self.assertEqual(data["local_marker"], "preserved")
        self.assertEqual(data["media_tools"]["ffmpeg"], "../../runtime/macos/bin/ffmpeg")
        self.assertEqual(data["jobs"]["trusted_account_news"]["visual_ocr"]["ffprobe_path"],
                         "../../runtime/macos/bin/ffprobe")

    def test_invalid_local_config_is_not_overwritten(self):
        self.local.write_text("[]")
        with self.assertRaises(RuntimeError):
            launcher.prepare()
        self.assertEqual(self.local.read_text(), "[]")

    def test_environment_uses_migrated_engine_and_tools(self):
        engine = self.root / "runtime/adu-motion-video/scripts/pipeline.py"
        engine.parent.mkdir(parents=True)
        engine.touch()
        env = launcher.environment("Haike_video")
        self.assertEqual(env["HAIKE_ADU_ROOT"], str(engine.parents[1]))
        self.assertEqual(env["FFMPEG_BINARY"], str(self.root / "runtime/macos/bin/ffmpeg"))
        self.assertEqual(env["PYTHONPATH"], str(self.root / "Haike_video"))


if __name__ == "__main__":
    unittest.main()
