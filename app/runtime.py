"""Process-wide dependencies. One uvicorn worker, so one Runtime. Tests install fakes with set_runtime()."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.config import Settings


@dataclass
class Runtime:
    settings: Settings
    store: Any  # app.store.Store
    bus: Any  # app.events.Bus
    cerebras: Any = None  # app.providers.cerebras.CerebrasClient
    openai: Any = None  # app.providers.openai_client.OpenAIClient


_runtime: Optional[Runtime] = None


def set_runtime(rt: Runtime) -> None:
    global _runtime
    _runtime = rt


def get_runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError("Runtime not initialised; create_app() lifespan or a test fixture must call set_runtime()")
    return _runtime
