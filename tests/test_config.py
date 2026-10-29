import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Cogs.core import config_tools


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / ".env"
        self.credentials = {"TELEGRAM_API_ID": "123456", "TELEGRAM_API_HASH": "a" * 32}

    def test_first_run_saves_then_new_environment_loads(self):
        first = config_tools.load_credentials(self.path, dict(self.credentials))
        second = config_tools.load_credentials(self.path, {})
        self.assertEqual(first, (123456, "a" * 32))
        self.assertEqual(first, second)

    def test_existing_file_is_loaded_without_rewriting(self):
        self.path.write_text('TELEGRAM_API_ID="123456"\nTELEGRAM_API_HASH="' + 'a' * 32 + '"\n', encoding="utf-8-sig")
        original = self.path.read_bytes()
        with patch.object(config_tools, "save_credentials") as save:
            self.assertEqual(config_tools.load_credentials(self.path, {}), (123456, "a" * 32))
            save.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)

    def test_updated_credentials_preserve_other_settings(self):
        self.path.write_text("# configurazione\nWEBNOWPLAYING_PORT=8976\nUNRELATED=value\n", encoding="utf-8")
        environment = dict(self.credentials)
        config_tools.load_credentials(self.path, environment)
        self.assertEqual(environment["WEBNOWPLAYING_PORT"], "8976")
        config_tools.load_credentials(self.path, {"TELEGRAM_API_HASH": "b" * 32})
        self.assertEqual(config_tools.load_credentials(self.path, {}), (123456, "b" * 32))
        self.assertIn("# configurazione\nWEBNOWPLAYING_PORT=8976\nUNRELATED=value\n", self.path.read_text(encoding="utf-8"))

    def test_invalid_override_never_overwrites_saved_credentials(self):
        config_tools.load_credentials(self.path, dict(self.credentials))
        original = self.path.read_bytes()
        for override in ({"TELEGRAM_API_HASH": "la_tua_api_hash"}, {"TELEGRAM_API_ID": "invalid"}):
            with self.assertRaises(ValueError) as error:
                config_tools.load_credentials(self.path, override)
            self.assertNotIn("a" * 32, str(error.exception))
            self.assertEqual(self.path.read_bytes(), original)

    def test_missing_credentials_do_not_create_file(self):
        with self.assertRaises(ValueError):
            config_tools.load_credentials(self.path, {})
        self.assertFalse(self.path.exists())

    def test_port_environment_has_priority(self):
        config_tools.load_credentials(self.path, dict(self.credentials))
        with self.path.open("a", encoding="utf-8") as output:
            output.write("WEBNOWPLAYING_PORT=8976\n")
        environment = {"WEBNOWPLAYING_PORT": "8977"}
        config_tools.load_credentials(self.path, environment)
        self.assertEqual(environment["WEBNOWPLAYING_PORT"], "8977")

    def test_lrclib_contact_loads_without_changing_other_credentials(self):
        config_tools.load_credentials(self.path, dict(self.credentials))
        with self.path.open("a", encoding="utf-8") as output:
            output.write("LRCLIB_CLIENT_CONTACT=https://example.com/melixsa\n")
        environment = {}
        config_tools.load_credentials(self.path, environment)
        self.assertEqual(environment["LRCLIB_CLIENT_CONTACT"], "https://example.com/melixsa")

    def test_failed_atomic_write_preserves_previous_file(self):
        config_tools.load_credentials(self.path, dict(self.credentials))
        original = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                config_tools.load_credentials(self.path, {"TELEGRAM_API_HASH": "b" * 32})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".env.*.tmp")), [])

    def test_geoseeer_key_loads_from_file_and_environment_takes_priority(self):
        config_tools.load_credentials(self.path, dict(self.credentials))
        with self.path.open("a", encoding="utf-8") as output:
            output.write("GEOSEEER_API_KEY=dummy-key\n")
        environment = {}
        config_tools.load_credentials(self.path, environment)
        self.assertEqual(environment["GEOSEEER_API_KEY"], "dummy-key")
        environment = {"GEOSEEER_API_KEY": "override-key"}
        config_tools.load_credentials(self.path, environment)
        self.assertEqual(environment["GEOSEEER_API_KEY"], "override-key")


if __name__ == "__main__":
    unittest.main()
