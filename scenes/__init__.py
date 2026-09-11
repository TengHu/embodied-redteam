"""Scene registry. Each module in this package defines `SCENE = Scene(...)`.

    scenes.load("living_room_approach_backflip")  -> the Scene
    scenes.names()        -> ["living_room_approach_backflip", ...]  (one per file)
"""

from __future__ import annotations

import importlib
from pathlib import Path

from scenes.base import Scene


def load(name: str) -> Scene:
    # Always re-read the module from disk so a live dev edit to a scene file is picked up on
    # the next session/fetch WITHOUT a server restart (uvicorn --reload hangs on live sessions).
    mod = importlib.import_module(f"scenes.{name}")
    return importlib.reload(mod).SCENE


def names() -> list[str]:
    here = Path(__file__).parent
    return sorted(p.stem for p in here.glob("*.py")
                  if p.stem not in ("__init__", "base"))
