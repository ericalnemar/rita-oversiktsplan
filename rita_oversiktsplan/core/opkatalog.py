"""Boverkets ÖP-katalog: de värden som en översiktsplans innehåll identifieras med. Ren Python.

Källa: Boverket, ÖP-katalogen (öppna data, CC0), medföljande kopia i ``data/opkatalog.json`` (uppdateras med
``tools/update_opkatalog.py``). Katalogen är ett träd: kategorier (nivå 1, t.ex. *Mark- och vattenanvändning*) med
värden under sig (nivå 2, t.ex. *Bostadsbebyggelse*). En kategori utan värden under sig (t.ex. *LIS*) är själv värdet.

I Lantmäteriets specifikation lagras ett värde ur katalogen som ``{varde, vardereferens, grupp, gruppreferens}``:
värdets namn och id, och namnet och id:t på kategorin (gruppen) det hör till. :class:`Value` har samma fyra delar.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple, Optional

DATA = Path(__file__).resolve().parent.parent / "data" / "opkatalog.json"


class Value(NamedTuple):
    varde: str
    vardereferens: str  # UUID
    grupp: str
    gruppreferens: str  # UUID
    beskrivning: str = ""


class Catalog:
    def __init__(self, data: dict):
        self.data = data
        katalog = data["katalog"]
        self.version: str = katalog["version"]
        self.categories: dict[str, dict] = {node["namn"]: node for node in katalog["data"]}

    def category(self, name: str) -> dict:
        try:
            return self.categories[name]
        except KeyError:
            raise KeyError(f"ÖP-katalogen {self.version} saknar kategorin {name!r}") from None

    def values(self, category: str, group: Optional[str] = None, itself: bool = False) -> tuple[Value, ...]:
        """Värdena i en kategori: värdena under den, eller kategorin själv om den inte har några (eller om
        ``itself`` anges: Utvecklingsinriktning är själv innehållstypen, och värdena under den är kompletterande
        utvecklingsinriktningar). ``group`` anger en annan kategori som grupp (riksintressena enligt miljöbalken
        delar värden med kommunens ställningstagande men har en egen grupp i katalogen)."""
        node = self.category(category)
        parent = self.category(group) if group else node
        children = [node] if itself else node.get("barn") or [node]
        return tuple(Value(child["namn"].strip(), child["id"], parent["namn"].strip(), parent["id"],
                           _attribute(child, "Beskrivning")) for child in children)

    def find(self, category: str, varde: str, group: Optional[str] = None, itself: bool = False) -> Optional[Value]:
        return next((v for v in self.values(category, group, itself) if v.varde == varde), None)


def _attribute(node: dict, name: str) -> str:
    for attribute in node.get("attribut") or []:
        if attribute.get("namn") == name and isinstance(attribute.get("data"), str):
            return attribute["data"].strip()
    return ""


@lru_cache(maxsize=1)
def bundled() -> Catalog:
    """Den medföljande kopian av katalogen."""
    return Catalog(json.loads(DATA.read_text(encoding="utf-8")))
