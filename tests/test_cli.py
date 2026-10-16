import sys
import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI

from app.cli import load_application, main


class CommandLineTests(unittest.TestCase):
    def test_factory_path_must_have_module_and_attribute(self) -> None:
        for value in ("", "module", ":factory", "module:"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    load_application(value)

    def test_loaded_factory_must_return_fastapi_app(self) -> None:
        module = types.ModuleType("test_cli_factory")
        module.build_app = lambda: FastAPI()
        module.not_an_app = lambda: object()
        sys.modules[module.__name__] = module
        try:
            self.assertIsInstance(
                load_application("test_cli_factory:build_app"), FastAPI
            )
            with self.assertRaises(TypeError):
                load_application("test_cli_factory:not_an_app")
        finally:
            del sys.modules[module.__name__]

    def test_terminal_entrypoint_requires_a_configured_factory(self) -> None:
        with patch.dict("os.environ", {"REALEZA_APP_FACTORY": ""}):
            with self.assertRaisesRegex(RuntimeError, "REALEZA_APP_FACTORY"):
                main()


if __name__ == "__main__":
    unittest.main()
