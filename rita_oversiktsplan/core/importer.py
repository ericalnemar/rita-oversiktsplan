"""Importera geometri från en annan datakälla till planens lager under *Att tilldela*.

Bara geometrin tas med, inga attribut: ytor hamnar i ``rita_otilldelad_yta``, linjer i ``rita_otilldelad_linje`` och
punkter i ``rita_otilldelad_punkt``, och tilldelas sedan innehåll som om de vore ritade. Geometrin omvandlas till
planens koordinatsystem (SWEREF 99 TM eller planens lokala zon), kurvor delas upp i raka segment och höjd- och M-värden tas bort. Ett objekt med
flera slags delar (en geometrisamling) delas upp efter slag; multipunkter blir en punkt per del, eftersom punktlagret
har enkla punkter. Objekten läggs i redigeringsbufferten och sparas med Spara (eller ångras med QGIS Ångra)."""
from __future__ import annotations

from dataclasses import dataclass, field

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry,
                       QgsProject, QgsVectorLayer, QgsVectorLayerUtils, QgsWkbTypes)

from . import model

_KIND = {
    QgsWkbTypes.GeometryType.PolygonGeometry: "polygon",
    QgsWkbTypes.GeometryType.LineGeometry: "line",
    QgsWkbTypes.GeometryType.PointGeometry: "point",
}


@dataclass
class ImportResult:
    counts: dict[str, int] = field(default_factory=lambda: {"polygon": 0, "line": 0, "point": 0})
    skipped: int = 0  # objekt utan geometri eller som inte kunde omvandlas
    invalid: int = 0  # importerade men ogiltiga geometrier (till exempel ytor som korsar sig själva)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def text(self) -> str:
        words = {"polygon": ("yta", "ytor"), "line": ("linje", "linjer"), "point": ("punkt", "punkter")}
        parts = [f"{n} {words[k][0] if n == 1 else words[k][1]}" for k, n in self.counts.items() if n]
        text = (", ".join(parts) if parts else "Inga geometrier") + " importerades till Att tilldela."
        if self.skipped:
            text += f" {self.skipped} objekt saknade geometri eller kunde inte omvandlas och hoppades över."
        if self.invalid:
            text += f" {self.invalid} geometrier är ogiltiga (till exempel ytor som korsar sig själva); kontrollera dem."
        return text


def clean_parts(geometry: QgsGeometry) -> list[tuple[str, QgsGeometry]]:
    """(slag, geometri) för en geometri utan kurvor, höjd- och M-värden, uppdelad efter slag. Punkter blir en per del."""
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return []
    geometry = QgsGeometry(geometry)  # kopia: källans objekt ändras inte
    abstract = geometry.get()
    if QgsWkbTypes.isCurvedType(geometry.wkbType()):
        geometry = QgsGeometry(abstract.segmentize())
        abstract = geometry.get()
    abstract.dropZValue()
    abstract.dropMValue()
    if QgsWkbTypes.flatType(geometry.wkbType()) == Qgis.WkbType.GeometryCollection:
        pieces = geometry.asGeometryCollection()
    else:
        pieces = [geometry]
    found: list[tuple[str, QgsGeometry]] = []
    grouped: dict[str, list[QgsGeometry]] = {}
    for piece in pieces:
        kind = _KIND.get(QgsWkbTypes.geometryType(piece.wkbType()))
        if kind is None or piece.isEmpty():
            continue
        if kind == "point":
            found += [("point", QgsGeometry(part)) for part in piece.asGeometryCollection()] if piece.isMultipart() \
                else [("point", piece)]
        else:
            grouped.setdefault(kind, []).append(piece)
    for kind, items in grouped.items():
        combined = QgsGeometry.collectGeometry(items) if len(items) > 1 else items[0]
        combined.convertToMultiType()
        found.append((kind, combined))
    return found


def import_geometries(source: QgsVectorLayer, targets: dict[str, QgsVectorLayer], selected_only: bool = False,
                      project: QgsProject | None = None) -> ImportResult:
    """Kopierar källans geometrier (inga attribut) till lagren under Att tilldela, i redigeringsbufferten."""
    project = project or QgsProject.instance()
    result = ImportResult()
    crs = next(iter(targets.values())).crs()  # planens koordinatsystem
    transform = QgsCoordinateTransform(source.crs(), crs, project) if source.crs().isValid() and source.crs() != crs \
        else None
    request = QgsFeatureRequest().setNoAttributes()
    if selected_only:
        request.setFilterFids(source.selectedFeatureIds())
    new: dict[str, list] = {kind: [] for kind in targets}
    for feature in source.getFeatures(request):
        geometry = QgsGeometry(feature.geometry())
        if transform is not None and not geometry.isNull():
            try:
                if geometry.transform(transform) != 0:
                    result.skipped += 1
                    continue
            except Exception:  # QgsCsException: punkter utanför koordinatsystemets område
                result.skipped += 1
                continue
        parts = clean_parts(geometry)
        if not parts:
            result.skipped += 1
            continue
        for kind, part in parts:
            target = targets.get(kind)
            if target is None:
                result.skipped += 1
                continue
            if not part.isGeosValid():
                result.invalid += 1
            new[kind].append(QgsVectorLayerUtils.createFeature(target, part, {}))
    for kind, features in new.items():
        if not features:
            continue
        target = targets[kind]
        if not target.isEditable():
            target.startEditing()
        target.beginEditCommand(f"Importera geometri från {source.name()}")
        ok = target.addFeatures(features)
        target.endEditCommand()
        if ok:
            result.counts[kind] += len(features)
        else:
            result.skipped += len(features)
    return result
