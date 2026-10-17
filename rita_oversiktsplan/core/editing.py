"""Redigering och markering i en plan: pennan (börja och avsluta redigeringen i alla planens lager), och markera,
avmarkera och kopiera innehåll mellan objekt, som motsvarande verktyg i Rita Detaljplan."""
from __future__ import annotations

from qgis.core import QgsFeatureRequest, QgsGeometry, QgsRectangle, QgsVectorLayer

from . import model
from .content import Assignment, Candidate, plain
from .project import draft_layers, layer_in_group


# -- pennan -----------------------------------------------------------------------------------------------------------
def plan_layers(group) -> list[QgsVectorLayer]:
    """Alla vektorlager i planens grupp (även tabellerna utan geometri)."""
    return [node.layer() for node in group.findLayers() if isinstance(node.layer(), QgsVectorLayer)]


def geometry_layers(group) -> list[QgsVectorLayer]:
    """Planens lager med geometri som man ritar i: Att tilldela och innehållslagren."""
    layers = [layer for layer in draft_layers(group).values() if layer is not None]
    for layer_def in model.CONTENT_LAYERS:
        layer = layer_in_group(group, layer_def.name)
        if layer is not None:
            layers.append(layer)
    return layers


def start_editing(group) -> int:
    """Öppnar alla planens lager för redigering. Returnerar antalet lager som inte gick att öppna."""
    failed = 0
    for layer in plan_layers(group):
        if not layer.isEditable() and not layer.startEditing():
            failed += 1
    return failed


def is_editing(group) -> bool:
    return any(layer.isEditable() for layer in plan_layers(group))


def has_edits(group) -> bool:
    return any(layer.isEditable() and layer.isModified() for layer in plan_layers(group))


def stop_editing(group, save: bool) -> list[str]:
    """Avslutar redigeringen i planens lager och sparar (eller kastar) ändringarna. Returnerar felen."""
    errors = []
    for layer in plan_layers(group):
        if not layer.isEditable():
            continue
        if save:
            if not layer.commitChanges():
                errors.append(f"{layer.name()}: " + "; ".join(layer.commitErrors()))
        else:
            layer.rollBack()
    return errors


# -- markera ----------------------------------------------------------------------------------------------------------
def _visible(group, layer: QgsVectorLayer) -> bool:
    node = group.findLayer(layer.id())
    return node is not None and node.isVisible()


def clear_selection(group) -> None:
    for layer in geometry_layers(group):
        layer.removeSelection()


def select(group, candidate: Candidate, add: bool = False) -> None:
    """Markerar ett objekt. Utan ``add`` tas annan markering i planen bort."""
    if not add:
        clear_selection(group)
    candidate.layer.select(candidate.fid)


def select_in_rect(group, rect: QgsRectangle, add: bool = False) -> int:
    """Markerar allt i planens synliga lager som rektangeln rör vid. Returnerar antalet."""
    if not add:
        clear_selection(group)
    probe = QgsGeometry.fromRect(rect)
    count = 0
    for layer in geometry_layers(group):
        if not _visible(group, layer):
            continue
        ids = [f.id() for f in layer.getFeatures(QgsFeatureRequest().setFilterRect(rect).setNoAttributes())
               if f.hasGeometry() and f.geometry().intersects(probe)]
        if ids:
            layer.select(ids)
            count += len(ids)
    return count


def selected_count(group) -> int:
    return sum(layer.selectedFeatureCount() for layer in geometry_layers(group))


# -- kopiera innehåll -------------------------------------------------------------------------------------------------
# Det som kopieras: samma fält som i Tilldela innehåll, utom namnet som hör till det enskilda objektet.
COPIED_FIELDS = ("innehallstyp_varde", "kompletterandeInnehallstyp", "precisering", "sambandsniva_varde",
                 "utbyggnadsordning")


def assignment_from(candidate: Candidate) -> Assignment:
    """Innehållet i ett tilldelat objekt, som en tilldelning som kan ges till ett annat objekt."""
    if candidate.category is None:
        raise ValueError("Objektet har inget innehåll att kopiera. Klicka på tilldelat innehåll.")
    feature = candidate.layer.getFeature(candidate.fid)
    values = {name: plain(feature[name]) for name in COPIED_FIELDS if feature.fields().indexOf(name) >= 0}
    return Assignment(candidate.category, values)


def describe(assignment: Assignment) -> str:
    value = assignment.values.get("innehallstyp_varde") or "innehållstyp ej vald"
    extra = assignment.values.get("kompletterandeInnehallstyp")
    return f"{assignment.category.alias}: {value}" + (f" ({extra})" if extra else "")
