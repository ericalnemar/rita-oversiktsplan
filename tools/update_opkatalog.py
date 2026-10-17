"""Hämtar den aktuella ÖP-katalogen från Boverkets öppna API och sparar den som pluginets medföljande kopia.

    python tools/update_opkatalog.py     # skriver rita_oversiktsplan/data/opkatalog.json (kräver nätverk)

Källa: Boverket, ÖP-katalogen (https://api.boverket.se/opmodell). Text och bild i API:et omfattas av CC0 enligt
Boverkets användarvillkor för API-tjänsten. Katalogen sparas som API:et levererar den (``/version/full/aktuell``),
inslagen i ett objekt med källa och hämtningsdatum. Ingen QGIS behövs.
"""
from __future__ import annotations

import datetime
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "rita_oversiktsplan" / "data" / "opkatalog.json"
API = "https://api.boverket.se/opmodell"
SOURCE = ("Boverket, ÖP-katalogen (https://api.boverket.se/opmodell). Text och bild omfattas av CC0 enligt "
          "Boverkets användarvillkor för API-tjänsten.")


def fetch(url: str) -> object:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "rita-oversiktsplan"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def wrap(katalog: dict, today: datetime.date) -> dict:
    return {"kalla": SOURCE, "hamtad": today.isoformat(), "katalog": katalog}


def main() -> None:
    katalog = fetch(f"{API}/version/full/aktuell")
    if not isinstance(katalog, dict) or not katalog.get("data"):
        raise SystemExit("Oväntat svar från ÖP-katalogens API")
    TARGET.write_text(json.dumps(wrap(katalog, datetime.date.today()), ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8", newline="\n")
    print(f"Skrev {TARGET.relative_to(ROOT)}: ÖP-katalogen version {katalog.get('version')}")


if __name__ == "__main__":
    main()
    sys.exit(0)
