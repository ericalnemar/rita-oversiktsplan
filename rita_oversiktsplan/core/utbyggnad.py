"""Utbyggnadsordning: planens etapper (namn och tidsperiod), som ställs in under Planens uppgifter och sedan går att
välja för mark- och vattenanvändning och utvecklingsinriktning (fältet ``utbyggnadsordning``), och som syns i kartan.

Etapperna sparas i planens metadatatabell (nyckeln ``utbyggnadsordning``, JSON), som standardvärdena, så att de följer
med en plan i en databas vid ut- och incheckning utan att tabellerna ändras. Objektets fält får etappens hela text,
till exempel ``Etapp 1 (2027–2035)``: det är den som följer med i exporten till Lantmäteriet (fritext i formatet).
Byter en etapp namn eller period får objekten den nya texten.

Ordningen i listan är utbyggnadsordningen: den första etappen ritas mörkast i kartan och de senare ljusare (se
:func:`symbology.apply_stages`). Mark- och vattenanvändning utan etapp är befintlig eller bevarad användning och ritas
som förut.

Ren Python utom :func:`refresh` och :func:`rename_in_plan`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

KEY = "utbyggnadsordning"  # i metadatatabellen och fältnamnet i innehållet
FIELD = "utbyggnadsordning"
CATEGORIES = ("markochvattenanvandning", "utvecklingsinriktning")  # grupperna som har fältet


@dataclass(frozen=True)
class Stage:
    namn: str
    period: str = ""

    @property
    def label(self) -> str:
        """Texten i objektets fält och i kartans teckenförklaring."""
        return f"{self.namn} ({self.period})" if self.period else self.namn


def parse(text: str) -> list[Stage]:
    """Etapperna ur metadatan (tom eller trasig text ger inga etapper)."""
    try:
        rows = json.loads(text or "[]")
    except ValueError:
        return []
    stages = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and str(row.get("namn") or "").strip():
            stages.append(Stage(str(row["namn"]).strip(), str(row.get("period") or "").strip()))
    return stages


def dump(stages: list[Stage]) -> str:
    return json.dumps([{"namn": s.namn, "period": s.period} for s in stages], ensure_ascii=False)


def check(stages: list[Stage]) -> None:
    """Två etapper får inte ha samma text, eftersom objekten känns igen på texten."""
    labels = [s.label for s in stages]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise ValueError(f"Två etapper heter likadant: {', '.join(duplicates)}. Ge dem olika namn eller perioder.")


def renames(old: list[Stage], new: list[tuple[int | None, Stage]]) -> dict[str, str]:
    """Vilka texter som byts: ``new`` är (index i den gamla listan eller None för en ny etapp, etappen)."""
    return {old[index].label: stage.label for index, stage in new
            if index is not None and 0 <= index < len(old) and old[index].label != stage.label}


# -- planen (QGIS) -----------------------------------------------------------------------------------------------------
def read(group) -> list[Stage]:
    from .project import plan_storage
    return parse(plan_storage(group).read_meta().get(KEY, ""))


def write(group, stages: list[Stage]) -> None:
    from .project import plan_storage
    check(stages)
    plan_storage(group).write_meta({KEY: dump(stages)})


def _layers(group):
    from . import model
    from .project import layer_in_group
    for category in model.CATEGORIES:
        if category.key in CATEGORIES:
            for layer_def in model.CONTENT_LAYERS:
                if layer_def.category == category:
                    layer = layer_in_group(group, layer_def.name)
                    if layer is not None:
                        yield layer_def, layer


def rename_in_plan(group, mapping: dict[str, str]) -> int:
    """Ger objekten etappens nya text (i redigeringsbufferten om lagret redigeras, annars sparat direkt). Returnerar
    antalet ändrade objekt."""
    if not mapping:
        return 0
    changed = 0
    for _, layer in _layers(group):
        index = layer.fields().indexOf(FIELD)
        if index < 0:
            continue
        updates = {f.id(): mapping[str(f[FIELD])] for f in layer.getFeatures() if str(f[FIELD]) in mapping}
        if not updates:
            continue
        started = not layer.isEditable() and layer.startEditing()
        for fid, value in updates.items():
            layer.changeAttributeValue(fid, index, value)
        if started and not layer.commitChanges():
            raise ValueError(f"Kunde inte spara {layer.name()}: " + "; ".join(layer.commitErrors()))
        changed += len(updates)
    return changed


def refresh(group, stages: list[Stage] | None = None) -> None:
    """Etapperna i formulärens lista och i kartan (mark- och vattenanvändningens ytor), efter en ändring."""
    from . import symbology
    from .project import plan_storage
    stages = read(group) if stages is None else stages
    lookups = {lookup.name: plan_storage(group).read_lookup(lookup) for lookup in _lookups()}
    for layer_def, layer in _layers(group):
        symbology.set_stage_widget(layer, stages)
        if layer_def.category.key == "markochvattenanvandning":
            symbology.apply(layer, layer_def.category, lookups, stages)
        layer.triggerRepaint()


def _lookups():
    from . import model
    return model.LOOKUPS
