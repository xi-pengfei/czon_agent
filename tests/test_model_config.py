import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.auth_store import AuthStore
from core.llm import get_provider_configs, make_llm_from_config


class ModelConfigTests(unittest.TestCase):
    def test_custom_openai_compatible_provider_is_accepted(self):
        providers = get_provider_configs({
            "providers": {
                "internal_model": {
                    "display_name": "Internal",
                    "base_url": "http://llm.internal/v1",
                    "model": "company-model",
                    "api_key": "test-secret",
                    "supports_vision": False,
                }
            }
        })
        self.assertEqual(providers["internal_model"]["model"], "company-model")

    def test_model_is_loaded_from_shared_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AuthStore(root / "data" / "models.db")
            store.upsert_model({
                "name": "internal_model",
                "display_name": "Internal",
                "base_url": "http://llm.internal/v1",
                "model": "company-model",
                "api_key": "test-secret",
                "supports_vision": False,
                "enabled": True,
            }, actor="test")
            config = {
                "active_provider": "internal_model",
                "agent": {"llm_request_timeout_seconds": 10},
                "webui": {"session_db": "./data/models.db"},
            }

            llm = make_llm_from_config(config, root)

            self.assertEqual(llm.provider, "internal_model")
            self.assertEqual(llm.model, "company-model")

    def test_model_uses_split_timeouts_and_bounded_retries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AuthStore(root / "data" / "models.db")
            store.upsert_model({
                "name": "internal_model", "display_name": "Internal",
                "base_url": "http://llm.internal/v1", "model": "company-model",
                "api_key": "test-secret", "supports_vision": False, "enabled": True,
            }, actor="test")
            config = {
                "active_provider": "internal_model",
                "agent": {
                    "llm_connect_timeout_seconds": 7,
                    "llm_read_timeout_seconds": 61,
                    "llm_write_timeout_seconds": 19,
                    "llm_max_retries": 1,
                },
                "webui": {"session_db": "./data/models.db"},
            }
            with patch("core.llm.httpx.Client") as http_client, patch("core.llm.OpenAI") as openai_client:
                make_llm_from_config(config, root)

            timeout = http_client.call_args.kwargs["timeout"]
            self.assertEqual((timeout.connect, timeout.read, timeout.write, timeout.pool), (7, 61, 19, 7))
            self.assertEqual(openai_client.call_args.kwargs["max_retries"], 1)

    def test_legacy_request_timeout_remains_supported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AuthStore(root / "data" / "models.db")
            store.upsert_model({
                "name": "legacy", "display_name": "Legacy", "base_url": "http://llm.internal/v1",
                "model": "legacy", "api_key": "test-secret", "supports_vision": False, "enabled": True,
            }, actor="test")
            config = {
                "active_provider": "legacy", "agent": {"llm_request_timeout_seconds": 22},
                "webui": {"session_db": "./data/models.db"},
            }
            with patch("core.llm.httpx.Client") as http_client, patch("core.llm.OpenAI"):
                make_llm_from_config(config, root)
            self.assertEqual(http_client.call_args.kwargs["timeout"].read, 22)

    def test_runtime_provider_environment_overrides_cli_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AuthStore(root / "data" / "models.db")
            for name in ("first", "deepseek"):
                store.upsert_model({
                    "name": name, "display_name": name, "base_url": "http://llm.internal/v1",
                    "model": name, "api_key": f"{name}-secret", "supports_vision": False,
                    "enabled": True,
                }, actor="test")
            config = {
                "active_provider": "first", "agent": {"llm_request_timeout_seconds": 10},
                "webui": {"session_db": "./data/models.db"},
            }
            with patch.dict("os.environ", {"CZON_ACTIVE_PROVIDER": "deepseek"}):
                llm = make_llm_from_config(config, root)
            self.assertEqual(llm.provider, "deepseek")

    def test_model_key_does_not_fall_back_to_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = AuthStore(root / "data" / "models.db")
            store.upsert_model({
                "name": "database_only", "display_name": "Database only",
                "base_url": "http://llm.internal/v1", "model": "chat",
                "supports_vision": False, "enabled": True,
            }, actor="test")
            config = {
                "active_provider": "database_only",
                "agent": {"llm_request_timeout_seconds": 10},
                "webui": {"session_db": "./data/models.db"},
            }
            with patch.dict("os.environ", {"DATABASE_ONLY_API_KEY": "environment-secret"}):
                with self.assertRaisesRegex(RuntimeError, "API Key"):
                    make_llm_from_config(config, root)

if __name__ == "__main__":
    unittest.main()
