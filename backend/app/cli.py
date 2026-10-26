import importlib
import os
from collections.abc import Callable

from fastapi import FastAPI


def load_application(factory_path: str) -> FastAPI:
    """Carrega a fábrica de app configurada como 'modulo:funcao'."""
    module_name, separator, attribute_name = factory_path.partition(":")
    if not separator or not module_name or not attribute_name:
        raise ValueError(
            "REALEZA_APP_FACTORY deve usar o formato 'modulo:funcao'"
        )

    module = importlib.import_module(module_name)
    factory: Callable[[], FastAPI] | None = getattr(module, attribute_name, None)
    if not callable(factory):
        raise TypeError(
            f"A fábrica '{factory_path}' não existe ou não pode ser chamada"
        )

    app = factory()
    if not isinstance(app, FastAPI):
        raise TypeError(f"A fábrica '{factory_path}' não retornou uma aplicação FastAPI")
    return app


def main() -> None:
    """Ponto de entrada terminal; exige adaptadores reais, sem banco fictício."""
    factory_path = os.environ.get("REALEZA_APP_FACTORY")
    if not factory_path:
        raise RuntimeError(
            "Configure REALEZA_APP_FACTORY=modulo:funcao para apontar "
            "à fábrica que conecta os repositórios do banco."
        )

    import uvicorn

    uvicorn.run(load_application(factory_path), host="127.0.0.1", port=8000)
