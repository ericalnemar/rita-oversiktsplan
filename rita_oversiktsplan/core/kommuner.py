"""Sveriges kommuner med kommunkod (källa: SCB). Ren Python.

Översiktsplanen anger både kommunkod och kommunnamn (attributen ``kommunkod`` och ``kommunnamn`` i Lantmäteriets
specifikation)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Optional

DATA = Path(__file__).resolve().parent.parent / "data" / "kommuner.json"


class Kommun(NamedTuple):
    kod: str
    namn: str


@lru_cache(maxsize=1)
def all_kommuner() -> tuple[Kommun, ...]:
    """Alla kommuner, sorterade på namn."""
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return tuple(Kommun(k["kod"], k["namn"]) for k in data["kommuner"])


def by_name(name: Optional[str]) -> Optional[Kommun]:
    wanted = (name or "").strip().lower()
    return next((k for k in all_kommuner() if k.namn.lower() == wanted), None)


def by_code(code: Optional[str]) -> Optional[Kommun]:
    wanted = (code or "").strip()
    return next((k for k in all_kommuner() if k.kod == wanted), None)
