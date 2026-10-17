"""Programmets koppling till planen i QGIS: läser planens innehåll (även det som inte sparats än), markerar i kartan,
skapar innehåll utan geometri och sparar kopplingarna i planens dokumenttabeller (``core/documents.py``)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from qgis.core import QgsGeometry, QgsWkbTypes

from ..core import documents, model, styles
from ..core.content import plain
from ..core.project import is_read_only, layer_in_group, plan_storage
from . import session as ss

LAND_USE = "markochvattenanvandning"  # mark- och vattenanvändning: ska ha geometri och bör beskrivas i texten


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(v):02x}" for v in rgb)


def shape(geometry: Optional[QgsGeometry]) -> tuple[str, list]:
    """(slag, delar) för en geometri: "polygon" med ringar, "line" med linjer eller "point" med en punkt per del."""
    if geometry is None or geometry.isEmpty():
        return ss.NONE_KIND, []
    kind = QgsWkbTypes.geometryType(geometry.wkbType())
    multi = geometry.isMultipart()
    if kind == QgsWkbTypes.GeometryType.PolygonGeometry:
        polygons = geometry.asMultiPolygon() if multi else [geometry.asPolygon()]
        return "polygon", [[(p.x(), p.y()) for p in ring] for polygon in polygons for ring in polygon]
    if kind == QgsWkbTypes.GeometryType.LineGeometry:
        lines = geometry.asMultiPolyline() if multi else [geometry.asPolyline()]
        return "line", [[(p.x(), p.y()) for p in line] for line in lines]
    if kind == QgsWkbTypes.GeometryType.PointGeometry:
        points = geometry.asMultiPoint() if multi else [geometry.asPoint()]
        return "point", [[(p.x(), p.y())] for p in points]
    return ss.NONE_KIND, []


def plan_objects(group) -> list[ss.PlanObject]:
    """Planen och allt innehåll i planens innehållslager, i lagrens ordning."""
    found = []
    plan_layer = layer_in_group(group, model.OVERSIKTSPLAN.name)
    plan = next(plan_layer.getFeatures(), None) if plan_layer is not None else None
    if plan is not None and plain(plan["objektidentitet"]):
        found.append(ss.PlanObject(str(plan["objektidentitet"]), "Översiktsplan", "", plain(plan["planens_titel"]) or "",
                                   ss.PLAN_KIND))
    for layer_def in model.CONTENT_LAYERS:
        layer = layer_in_group(group, layer_def.name)
        if layer is None:
            continue
        category = layer_def.category
        field = styles.field_for(category.key)
        for feature in layer.getFeatures():
            identity = plain(feature["objektidentitet"])
            if not identity:
                continue
            value = plain(feature[field]) if layer.fields().indexOf(field) >= 0 else None
            value = value or plain(feature["innehallstyp_varde"]) or ""
            style = styles.style_for(category.key, value)
            kind, parts = shape(feature.geometry() if feature.hasGeometry() else None)
            found.append(ss.PlanObject(
                str(identity), category.alias, value, plain(feature["namn"]) or "", kind, parts,
                _hex(style.color) if style is not None else "#8a8f8d", bool(style is not None and style.filled),
                required_text=category.key == LAND_USE))
    return found


class QgisHost(ss.Host):
    name = "QGIS"

    def __init__(self, group):
        self.group = group

    def load_plan(self) -> ss.PlanData:
        storage = plan_storage(self.group)
        objects = plan_objects(self.group)
        plan = next((o for o in objects if o.kind == ss.PLAN_KIND), None)
        if plan is None:
            raise ValueError("Planens tabell är tom. Skapa planen med Ny översiktsplan.")
        layer = layer_in_group(self.group, model.OVERSIKTSPLAN.name)
        feature = next(layer.getFeatures())
        return ss.PlanData(plan.name or storage.name, plain(feature["kommunnamn"]) or "", storage.key,
                           storage.read_lookup(model.AVSNITTSTYP_LOOKUP), objects, storage.describe())

    def read_links(self, docx: Path) -> dict[str, ss.SavedSection]:
        return {bookmark: ss.SavedSection(links.type, set(links.identities))
                for bookmark, links in documents.read_links(self.group, docx).items()}

    def linked_documents(self) -> list[Path]:
        return documents.linked_documents(self.group)

    def save(self, docx: Path, sections: list[ss.SectionToSave]) -> None:
        if is_read_only(self.group):
            raise ValueError("Planen ligger i databasen och är skrivskyddad. Checka ut den i Rita Översiktsplan först.")
        documents.save(self.group, docx, [documents.SectionLinks(s.bookmark, s.heading, s.type, set(s.identities))
                                          for s in sections])

    def selected_identities(self) -> list[str]:
        return documents.selected_identities(self.group)

    def select_in_map(self, identities: set[str]) -> int:
        return documents.select_in_map(self.group, identities)

    def create_without_geometry(self, heading: str, parent=None) -> Optional[ss.PlanObject]:
        """Frågar efter grupp och innehållstyp (samma dialog som Tilldela innehåll) och skapar innehållet."""
        from ..core import content
        from ..gui.assign_dialog import AssignDialog

        if is_read_only(self.group):
            raise ValueError("Planen ligger i databasen och är skrivskyddad. Checka ut den i Rita Översiktsplan först.")
        storage = plan_storage(self.group)
        lookups = {lookup.name: storage.read_lookup(lookup) for lookup in model.LOOKUPS}
        dialog = AssignDialog(model.NO_GEOMETRY, lookups, parent=parent)
        dialog.namn.setText(heading)
        if not dialog.exec():
            return None
        identity = content.create_without_geometry(self.group, dialog.assignment())
        return next((o for o in plan_objects(self.group) if o.identity == identity), None)
