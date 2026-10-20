"""Kommunens yta som plangeometri: hämtas från Lantmäteriets kommunytor när en ny översiktsplan skapas (valfritt i
dialogen Ny översiktsplan; den som vill rita en mindre plangeometri själv kryssar ur rutan).

Källa: Lantmäteriets kommunytor (utan enklaver) i länsstyrelsernas nationella visningstjänst
(``ext-geodata-nationella-visning.lansstyrelsen.se``, ``LM/LM_Admin_granser_EXT``, lager 0, fältet ``KOMMUNKOD``),
läst 2026-10-20. Ytan skrivs in i planens GeoPackage när planen skapas (:func:`geopackage.create_geopackage`), så att
det fungerar både för en plan i en fil och i en databas.

Den här modulen är ren Python utom :func:`plan_area`.
"""
from __future__ import annotations

from typing import Callable, Optional

from .riksintressen import FetchError, fetch_layer

LST = "https://ext-geodata-nationella-visning.lansstyrelsen.se/arcgis/rest/services"
MUNICIPALITY = (f"{LST}/LM/LM_Admin_granser_EXT/MapServer", 0)  # LM Kommunytor (utan enklaver)
PLAN_AREA = "innehall_op_plangeometri"


def municipality_where(kommunkod: str) -> str:
    if not (kommunkod.isdigit() and len(kommunkod) == 4):
        raise ValueError(f"Kommunkoden {kommunkod!r} har inte fyra siffror.")
    return f"KOMMUNKOD='{kommunkod}'"


def fetch_municipality(get: Callable[[str], str], kommunkod: str, epsg: int,
                       progress: Optional[Callable[[str], None]] = None) -> list[dict]:
    """Kommunens yta (GeoJSON-geometrier i planens koordinatsystem, oftast en) ur Lantmäteriets kommunytor."""
    service, layer = MUNICIPALITY
    found = fetch_layer(get, service, layer, None, epsg, "kommunens yta", progress,
                        where=municipality_where(kommunkod), owner="länsstyrelsernas tjänst")
    if not found:
        raise FetchError(f"Hittade ingen kommun med koden {kommunkod} i Lantmäteriets kommunytor.")
    return [geometry for _, geometry in found]


def plan_area(group):
    """Planens avgränsning: plangeometrins ytor sammanslagna (även osparade), eller None."""
    from qgis.core import QgsGeometry

    from .project import layer_in_group
    layer = layer_in_group(group, PLAN_AREA)
    shapes = [f.geometry() for f in layer.getFeatures() if f.hasGeometry()] if layer is not None else []
    return QgsGeometry.unaryUnion(shapes) if shapes else None
