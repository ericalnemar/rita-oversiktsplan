"""Lägger in en översiktsplans lager i ett QGIS-projekt och ställer in formulär, standardvärden och utseende."""
from __future__ import annotations

from pathlib import Path

from qgis.core import (QgsCoordinateReferenceSystem, QgsDefaultValue, QgsEditFormConfig, QgsEditorWidgetSetup,
                       QgsFieldConstraints, QgsProject, QgsVectorLayer)

from . import model, symbology
from .storage import GeoPackageStorage, PostgisError, PostgisStorage, Storage, as_storage, from_key

PLAN_PROPERTY = "rita_oversiktsplan/plan"  # på planens grupp: GeoPackage-filens sökväg, eller planens plats i databasen
CHECKOUT_PATH_PROPERTY = "rita_oversiktsplan/checkout_path"  # på gruppen: den lokala kopian när planen är utcheckad
CHECKOUT_TOKEN_PROPERTY = "rita_oversiktsplan/checkout_token"
TABLE_PROPERTY = "rita_oversiktsplan/table"  # på varje lager: tabellnamnet, så att lagret hittas även om det döps om
DOCUMENTS_GROUP = "Beslut, dokument och underlag"
DRAFTS_GROUP = "Att tilldela"


class PlanError(ValueError):
    """Filen går inte att öppna som en översiktsplan från pluginet."""


def plan_groups(project: QgsProject) -> list:
    return [g for g in project.layerTreeRoot().findGroups(True) if g.customProperty(PLAN_PROPERTY)]


def _key(source) -> str:
    if isinstance(source, Storage):
        return source.key if source.kind != "geopackage" else str(source.path.resolve())
    return str(Path(source).resolve())


def find_plan_group(project: QgsProject, source):
    """Gruppen för en plan (sökväg eller ``Storage``) som redan är öppen, eller None."""
    wanted = _key(source)
    return next((g for g in plan_groups(project) if g.customProperty(PLAN_PROPERTY) == wanted), None)


def active_plan_group(project: QgsProject, current_layer=None):
    """Planen som kommandona gäller: den som det markerade lagret hör till, annars den översta planen i
    lagerpanelen. None om ingen plan är öppen."""
    groups = plan_groups(project)
    if current_layer is not None:
        node = project.layerTreeRoot().findLayer(current_layer.id())
        while node is not None:
            if node in groups:
                return node
            node = node.parent()
    return groups[0] if groups else None


def layer_in_group(group, table: str) -> QgsVectorLayer | None:
    """Lagret för en tabell i planens grupp (även i undergrupperna), oavsett vad lagret heter i lagerpanelen."""
    for node in group.findLayers():
        layer = node.layer()
        if layer is not None and layer.customProperty(TABLE_PROPERTY) == table:
            return layer
    return None


def drawing_order(layer_defs: list) -> list:
    """Punkt överst, sedan linje och yta underst i lagerpanelen: det översta lagret ritas överst, så ytor får inte
    täcka linjer och punkter."""
    rank = {"Point": 0, "MultiLineString": 1, "MultiPolygon": 2}
    return sorted(layer_defs, key=lambda d: rank.get(d.geometry, 3))


def category_order() -> list:
    """Innehållstyperna i lagerpanelen: mark- och vattenanvändningen sist (underst), eftersom den är grunden och
    nästan täckande; övrigt innehåll är genomskinliga tillägg ovanpå."""
    base = [c for c in model.CATEGORIES if c.key == "markochvattenanvandning"]
    return [c for c in model.CATEGORIES if c not in base] + base


def load_plan(source, project: QgsProject) -> dict[str, QgsVectorLayer]:
    """Lägger till planens lager i ``project``, i en egen grupp överst i lagerpanelen, och ställer in dem. ``source``
    är en GeoPackage (sökväg) eller ett ``Storage`` (en plan i en databas, som då är skrivskyddad tills den checkas
    ut). Returnerar lagren per tabellnamn."""
    plan_storage_ = as_storage(source)
    if isinstance(plan_storage_, GeoPackageStorage):
        plan_storage_ = GeoPackageStorage(plan_storage_.path.resolve())
        from . import geopackage
        if geopackage.read_meta(plan_storage_.path) and geopackage.upgrade(plan_storage_.path):
            pass  # äldre plan: det som saknas är tillagt
    elif isinstance(plan_storage_, PostgisStorage):
        try:
            plan_storage_.upgrade()  # ett schema från en äldre version: saknade kolumner läggs till
        except PostgisError as exc:
            raise PlanError(str(exc)) from exc
    what = plan_storage_.describe()
    meta = plan_storage_.read_meta()
    if not meta:
        raise PlanError(f"{what} är inte en översiktsplan skapad med Rita Översiktsplan")
    if meta.get("schema_version") != str(model.SCHEMA_VERSION):
        raise PlanError(f"{what} är skapad med en annan version av pluginet (schema {meta.get('schema_version')}, "
                        f"den här versionen läser schema {model.SCHEMA_VERSION})")
    if find_plan_group(project, plan_storage_) is not None:
        raise PlanError(f"{what} är redan öppen i projektet")

    if not project.mapLayers():  # ett tomt projekt får planens koordinatsystem; rör inte en öppen karta
        project.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{plan_storage_.epsg}"))

    root = project.layerTreeRoot()
    group = root.insertGroup(0, f"Översiktsplan – {plan_storage_.name}")
    group.setCustomProperty(PLAN_PROPERTY, _key(plan_storage_))

    layers: dict[str, QgsVectorLayer] = {}

    def add(layer_def: model.LayerDef, parent) -> QgsVectorLayer:
        uri, provider = plan_storage_.layer_source(layer_def)
        layer = QgsVectorLayer(uri, layer_def.alias, provider)
        if not layer.isValid():
            raise PlanError(f"Kunde inte läsa tabellen {layer_def.name} i {what}")
        layer.setCustomProperty(TABLE_PROPERTY, layer_def.name)
        project.addMapLayer(layer, False)
        parent.addLayer(layer)
        layers[layer_def.name] = layer
        return layer

    add(model.OVERSIKTSPLAN, group)
    drafts = group.addGroup(DRAFTS_GROUP)  # överst: det man ritar hamnar här tills det fått innehåll
    for layer_def in drawing_order(list(model.DRAFT_LAYERS.values())):
        _suppress_form(add(layer_def, drafts))
    for category in category_order():
        defs = [d for d in model.CONTENT_LAYERS if d.category == category]
        parent = group if category.polygon_only else group.addGroup(category.alias)
        for layer_def in drawing_order(defs):
            add(layer_def, parent)
        if not category.polygon_only:
            parent.setExpanded(False)
    documents = group.addGroup(DOCUMENTS_GROUP)
    for layer_def in (model.BESLUT, *model.DOCUMENT_TABLES):
        add(layer_def, documents)
    documents.setExpanded(False)

    lookups = {lookup.name: plan_storage_.read_lookup(lookup) for lookup in model.LOOKUPS}
    plan_layer = layers[model.OVERSIKTSPLAN.name]
    feature = next(plan_layer.getFeatures(), None)
    title = feature["planens_titel"] if feature is not None else None
    if title not in (None, "") and not _is_null(title):
        group.setName(f"Översiktsplan – {title}")
    for layer_def in model.LAYERS:
        _configure_fields(layers[layer_def.name], layer_def, lookups, plan_layer)
        if layer_def.category is not None:
            symbology.apply(layers[layer_def.name], layer_def.category, lookups)
    for layer_def in model.DRAFT_LAYERS.values():
        symbology.apply_draft(layers[layer_def.name])
    if plan_storage_.read_only:
        for layer in layers.values():
            layer.setReadOnly(True)  # en plan i databasen redigeras i en utcheckad kopia
            hide_plan_column(layer)
    return layers


def draft_layers(group) -> dict[str, QgsVectorLayer]:
    """Planens lager för otilldelad geometri, per geometri (``polygon``, ``line``, ``point``)."""
    return {suffix: layer_in_group(group, layer_def.name) for suffix, layer_def in model.DRAFT_LAYERS.items()}


def hide_plan_column(layer: QgsVectorLayer) -> None:
    """Kolumnen ``plan`` i databasens tabeller skiljer planerna åt; den visas inte i formulär och attributtabell."""
    index = layer.fields().indexOf("plan")
    if index >= 0:
        layer.setEditorWidgetSetup(index, QgsEditorWidgetSetup("Hidden", {}))


def plan_storage(group) -> Storage:
    """Där planens data ligger just nu: GeoPackage-filen, den lokala kopian om planen är utcheckad, eller databasen."""
    local = group.customProperty(CHECKOUT_PATH_PROPERTY)
    if local and group.customProperty(CHECKOUT_TOKEN_PROPERTY):
        return GeoPackageStorage(local)
    return from_key(group.customProperty(PLAN_PROPERTY) or "")


def is_read_only(group) -> bool:
    """Planen läses direkt från databasen och måste checkas ut innan den ändras."""
    return plan_storage(group).read_only


def _suppress_form(layer: QgsVectorLayer) -> None:
    """Inget formulär när man ritar: otilldelad geometri har inga uppgifter att fylla i."""
    config = layer.editFormConfig()
    config.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
    layer.setEditFormConfig(config)


def _configure_fields(layer: QgsVectorLayer, layer_def: model.LayerDef, lookups: dict[str, list[str]],
                      plan_layer: QgsVectorLayer) -> None:
    not_null = QgsFieldConstraints.Constraint.ConstraintNotNull
    unique = QgsFieldConstraints.Constraint.ConstraintUnique
    soft = QgsFieldConstraints.ConstraintStrength.ConstraintStrengthSoft
    hard = QgsFieldConstraints.ConstraintStrength.ConstraintStrengthHard
    fid = layer.fields().indexOf("fid")
    if fid >= 0:  # GeoPackagens interna radnummer, inte planens identitet (den är objektidentitet)
        layer.setEditorWidgetSetup(fid, QgsEditorWidgetSetup("Hidden", {}))
    for field in layer_def.fields:
        idx = layer.fields().indexOf(field.name)
        if idx < 0:
            raise PlanError(f"Fältet {field.name} saknas i tabellen {layer_def.name}")
        layer.setFieldAlias(idx, field.alias)
        default = _default_expression(layer_def, field, plan_layer)
        if default:
            layer.setDefaultValueDefinition(idx, QgsDefaultValue(default, False))
        if field.required:
            layer.setFieldConstraint(idx, not_null, soft)
        owns_identity = layer_def.category is not None or layer_def is model.OVERSIKTSPLAN
        if field.name == "objektidentitet" and owns_identity:  # i dokumentavsnitt är det en hänvisning, inte unik
            layer.setFieldConstraint(idx, unique, hard)
        layer.setEditorWidgetSetup(idx, _widget_setup(field, lookups))
        if field.name == "objektidentitet" and owns_identity:
            # objektets UUID syns i formuläret och attributtabellen men går inte att ändra: pluginet sätter det, och
            # exporten, kopplingarna och planhandlingens bokmärken hänvisar till det
            layer.setEditorWidgetSetup(idx, QgsEditorWidgetSetup("TextEdit", {}))
            form = layer.editFormConfig()
            form.setReadOnly(idx, True)
            layer.setEditFormConfig(form)


def _default_expression(layer_def: model.LayerDef, field: model.FieldDef, plan_layer: QgsVectorLayer) -> str | None:
    if layer_def.category is not None and field.name in ("planhandelse_varde", "planhandelse_datum"):
        # nytt innehåll får planens aktuella planhändelse (en GeoPackage = en översiktsplan)
        return f"aggregate('{plan_layer.id()}', 'max', \"{field.name}\")"
    return field.default


def _widget_setup(field: model.FieldDef, lookups: dict[str, list[str]]) -> QgsEditorWidgetSetup:
    if field.hidden:
        return QgsEditorWidgetSetup("Hidden", {})
    choices = lookups.get(field.lookup) if field.lookup else field.choices
    if choices:
        return QgsEditorWidgetSetup("ValueMap", {"map": [{value: value} for value in choices]})
    if field.type == model.BOOL:
        return QgsEditorWidgetSetup("CheckBox", {})
    if field.type == model.DATE:
        return QgsEditorWidgetSetup("DateTime", {"allow_null": True, "calendar_popup": True,
                                                 "display_format": "yyyy-MM-dd", "field_format": "yyyy-MM-dd"})
    if field.type == model.DATETIME:
        return QgsEditorWidgetSetup("DateTime", {"allow_null": True, "calendar_popup": True,
                                                 "display_format": "yyyy-MM-dd HH:mm:ss",
                                                 "field_format": "yyyy-MM-dd HH:mm:ss"})
    if field.multiline:
        return QgsEditorWidgetSetup("TextEdit", {"IsMultiline": True})
    return QgsEditorWidgetSetup("TextEdit", {})


def _is_null(value) -> bool:
    return hasattr(value, "isNull") and value.isNull()
