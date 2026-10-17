"""Programmets tillstånd: planen, planhandlingen, avsnittens avsnittstyp och status, och kopplingarna mellan avsnitt
och planens objekt. Ren Python (inget Qt och inget QGIS), så att det går att testa för sig.

Planen hämtas från en *värd* (``Host``): i pluginet är det QGIS (``host.QgisHost``). Värden ger planens objekt och
sparar kopplingarna i planens tabeller."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core import planhandling as ph
from ..core import planhandling_html as ph_html

# avsnittens status i steget Avsnitt
FORSLAG, ANDRAD, GRANSKAD, HOPPAS = "forslag", "andrad", "granskad", "hoppas"
STATUS_TEXT = {FORSLAG: "Förslag", ANDRAD: "Ändrad", GRANSKAD: "Granskad", HOPPAS: "Inget bokmärke"}
NEEDS_LOOK = (FORSLAG, ANDRAD)

# kontrollens allvarlighet
FEL, VARNING, INFO = "fel", "varning", "info"

PLAN_KIND = "plan"  # objektet är planen själv (oversiktsplan.dokument)
NONE_KIND = "none"  # innehåll utan geometri


class SessionError(ValueError):
    """Något gick inte att läsa eller spara. Meddelandet är avsett för användaren."""


@dataclass
class PlanObject:
    """Ett objekt i planen som ett avsnitt kan kopplas till."""
    identity: str
    category: str  # gruppens namn, t.ex. "Klimatrelaterade risker"; "Översiktsplan" för planen
    value: str  # innehållstypen (ÖP-katalogens värde)
    name: str = ""
    kind: str = NONE_KIND  # "polygon", "line", "point", NONE_KIND eller PLAN_KIND
    parts: list = field(default_factory=list)  # [[(x, y), …], …] i planens koordinater
    color: str = "#888888"
    filled: bool = False  # heltäckande yta (mark- och vattenanvändning)
    required_text: bool = False  # bör beskrivas i planhandlingen (mark- och vattenanvändning)

    def title(self) -> str:
        if self.kind == PLAN_KIND:
            return "Hela planen"
        text = self.value or "innehållstyp ej vald"
        return f"{text} ({self.name})" if self.name else text

    def long_title(self) -> str:
        if self.kind == PLAN_KIND:
            return f"Hela planen ({self.name})" if self.name else "Hela planen"
        where = " · utan geometri" if self.kind == NONE_KIND else ""
        return f"{self.category}: {self.title()}{where}"


@dataclass
class PlanData:
    title: str
    kommun: str
    path: str  # var planen ligger (GeoPackage-filen eller planens plats i databasen), nyckel för senaste dokument
    types: list[str]  # avsnittstyperna i planens katalogversion
    objects: list[PlanObject] = field(default_factory=list)
    source: str = ""  # var planen ligger, för människor (filnamnet eller anslutning · schema · plan)

    def object(self, identity: str) -> Optional[PlanObject]:
        return next((o for o in self.objects if o.identity == identity), None)

    def plan_object(self) -> Optional[PlanObject]:
        return next((o for o in self.objects if o.kind == PLAN_KIND), None)


@dataclass
class SavedSection:
    """Det som redan är sparat i planen för ett bokmärke."""
    type: str
    identities: set[str]


@dataclass
class SectionToSave:
    bookmark: str
    heading: str
    type: str
    identities: set[str]


@dataclass
class Finding:
    level: str  # FEL, VARNING eller INFO
    text: str
    where: str = ""
    section: Optional[int] = None  # avsnittet fyndet gäller (Gå till)
    identity: Optional[str] = None  # objektet fyndet gäller


def _names(objects: list[PlanObject], limit: int = 4) -> str:
    names = [o.long_title() for o in objects[:limit]]
    rest = len(objects) - limit
    return "; ".join(names) + (f" och {rest} till" if rest > 0 else "")


class Host:
    """Planen som programmet arbetar med. Implementeras av QGIS-värden; testerna har en egen."""
    name = "QGIS"

    def load_plan(self) -> PlanData:
        raise NotImplementedError

    def read_links(self, docx: Path) -> dict[str, SavedSection]:
        raise NotImplementedError

    def save(self, docx: Path, sections: list[SectionToSave]) -> None:
        raise NotImplementedError

    def linked_documents(self) -> list[Path]:
        """Dokument som planen redan har kopplingar till, senast sparade först."""
        return []

    def selected_identities(self) -> list[str]:
        return []

    def select_in_map(self, identities: set[str]) -> int:
        return 0

    def create_without_geometry(self, heading: str, parent=None) -> Optional[PlanObject]:
        return None


class Store:
    """Inställningar som sparas mellan gångerna (senaste fil). ``get``/``put`` kommer från QSettings i fönstret."""

    def __init__(self, get: Optional[Callable] = None, put: Optional[Callable] = None):
        self._memory: dict = {}
        self._get = get or self._memory.get
        self._put = put or self._memory.__setitem__

    def get(self, key: str) -> Optional[str]:
        return self._get(key)

    def put(self, key: str, value: str) -> None:
        self._put(key, value)


class Session:
    def __init__(self, host: Host, store: Optional[Store] = None):
        self.host = host
        self.store = store or Store()
        self.plan: Optional[PlanData] = None
        self.document: Optional[ph.Document] = None
        self.docx: Optional[Path] = None
        self.types: dict[int, str] = {}  # avsnittets index → avsnittstyp
        self.reviewed: set[int] = set()
        self.changed_type: set[int] = set()
        self.skipped: set[int] = set()
        self.links: dict[int, set[str]] = {}
        self.saved_from: set[int] = set()  # avsnitt vars typ och kopplingar lästes ur planen
        self.dirty = False
        self.saved_to: Optional[Path] = None
        self.other_document: Optional[Path] = None  # en planhandling med bokmärken som planen redan har kopplingar till

    # -- läsa ---------------------------------------------------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self.plan is not None and self.document is not None

    @property
    def sections(self) -> list[ph.Section]:
        return self.document.sections if self.document else []

    def load_plan(self) -> PlanData:
        """Läser planen (igen) från värden. Kopplingarna i programmet behålls."""
        try:
            self.plan = self.host.load_plan()
        except ValueError as exc:
            raise SessionError(str(exc)) from exc
        return self.plan

    def recent_key(self) -> str:
        return f"senast/{self.plan.path}" if self.plan else "senast/docx"

    def recent_docx(self) -> Optional[Path]:
        value = self.store.get(self.recent_key())
        return Path(value) if value and Path(value).exists() else None

    def load_docx(self, path: str | Path) -> None:
        """Läser planhandlingen, föreslår avsnittstyper och hämtar det som redan är sparat för dokumentet i planen."""
        if self.plan is None:
            raise SessionError("Planen är inte inläst.")
        path = Path(path)
        try:
            document = ph.read(path, self.plan.types)
        except (ph.DocxError, OSError) as exc:
            raise SessionError(str(exc)) from exc
        try:
            saved = self.host.read_links(path)
        except ValueError as exc:
            raise SessionError(str(exc)) from exc
        self.document, self.docx = document, path
        self.types, self.links = {}, {}
        self.reviewed, self.changed_type, self.skipped, self.saved_from = set(), set(), set(), set()
        for section in document.sections:
            existing = saved.get(section.bookmark) if section.bookmark else None
            if existing is not None:
                self.types[section.index] = existing.type or section.suggested_type
                self.links[section.index] = set(existing.identities)
                self.saved_from.add(section.index)
                self.reviewed.add(section.index)
            else:
                self.types[section.index] = section.suggested_type
                self.links[section.index] = set()
                if not section.bookmark and not section.text:
                    self.skipped.add(section.index)  # bara en rubrik: inget att koppla
        self.dirty = False
        self.saved_to = None
        self.other_document = None
        if not any(s.bookmark for s in document.sections):
            # ett dokument utan bokmärken i en plan som redan har bokmärken: troligen originalet i stället för kopian med bokmärken
            try:
                self.other_document = next((d for d in self.host.linked_documents() if d != path), None)
            except ValueError:
                pass
        self.store.put(self.recent_key(), str(path))

    # -- avsnitten ------------------------------------------------------------------------------------------------------
    def status(self, index: int) -> str:
        if index in self.skipped:
            return HOPPAS
        if index in self.reviewed:
            return GRANSKAD
        return ANDRAD if index in self.changed_type else FORSLAG

    def tagged(self) -> list[ph.Section]:
        """Avsnitten som får bokmärken."""
        return [s for s in self.sections if s.index not in self.skipped]

    def counts(self) -> dict[str, int]:
        result = {key: 0 for key in STATUS_TEXT}
        for section in self.sections:
            result[self.status(section.index)] += 1
        return result

    def why(self, index: int) -> str:
        section = self.sections[index]
        if index in self.saved_from:
            return "Avsnittstypen och kopplingarna är sparade i planen sedan tidigare."
        if index in self.changed_type:
            return "Du har valt avsnittstypen."
        type_ = self.types[index]
        if section.reason == ph.LIKE:
            text = f"Rubriken liknar avsnittstypen \"{type_}\" i ÖP-katalogen."
        elif section.reason == ph.WORD:
            text = f"Rubriken innehåller \"{section.reason_word}\", som brukar höra till \"{type_}\"."
        elif section.reason == ph.INHERITED:
            parent = section.path[-2] if len(section.path) > 1 else ""
            text = f"Samma avsnittstyp som rubriken ovanför ({parent})."
        else:
            text = f"Inget i rubriken pekar på en annan typ, så förslaget är \"{type_}\"."
        if not section.text:
            text += " Rubriken har ingen egen text."
        return text

    def set_type(self, index: int, type_: str) -> None:
        if self.types.get(index) == type_:
            return
        self.types[index] = type_
        self.changed_type.add(index)
        self.reviewed.discard(index)
        self.saved_from.discard(index)
        self.skipped.discard(index)
        self.dirty = True

    def approve(self, index: int) -> None:
        self.reviewed.add(index)
        self.skipped.discard(index)
        self.dirty = True

    def skip(self, index: int, skip: bool = True) -> None:
        if skip:
            self.skipped.add(index)
        else:
            self.skipped.discard(index)
        self.dirty = True

    # -- kopplingar -----------------------------------------------------------------------------------------------------
    def link(self, index: int, identities) -> int:
        """Kopplar avsnittet till objekten. Returnerar antalet nya kopplingar. Ett avsnitt markerat Inget bokmärke
        får bokmärke nu."""
        before = len(self.links[index])
        self.links[index].update(identities)
        added = len(self.links[index]) - before
        if added:
            self.skipped.discard(index)
            self.dirty = True
        return added

    def unlink(self, index: int, identity: str) -> None:
        if identity in self.links[index]:
            self.links[index].discard(identity)
            self.dirty = True

    def toggle(self, index: int, identity: str) -> bool:
        """Kopplar eller kopplar loss ett objekt. Returnerar True om det blev kopplat."""
        if identity in self.links[index]:
            self.unlink(index, identity)
            return False
        self.link(index, [identity])
        return True

    def clear_links(self, index: int) -> None:
        if self.links[index]:
            self.links[index] = set()
            self.dirty = True

    def sections_for(self, identity: str) -> list[int]:
        """Avsnitten som är kopplade till ett objekt (åt andra hållet)."""
        return [s.index for s in self.tagged() if identity in self.links.get(s.index, set())]

    def linked_count(self) -> int:
        return sum(1 for s in self.tagged() if self.links[s.index])

    # -- kontroll -------------------------------------------------------------------------------------------------------
    def findings(self) -> list[Finding]:
        found: list[Finding] = []
        if not self.ready:
            return found
        known = {o.identity for o in self.plan.objects}
        tagged = self.tagged()
        linked = {i for s in tagged for i in self.links[s.index]}
        for section in tagged:
            missing = self.links[section.index] - known
            if missing:
                found.append(Finding(FEL, f"Avsnittet är kopplat till {len(missing)} objekt som inte finns i planen "
                                          "längre (borttagna eller i en annan plan). Ta bort kopplingarna eller läs om "
                                          "planen.", section.heading, section=section.index))
        review = [s for s in self.sections if self.status(s.index) in NEEDS_LOOK]
        if review:
            found.append(Finding(VARNING, f"{len(review)} avsnitt har en föreslagen avsnittstyp som inte är granskad.",
                                 review[0].heading, section=review[0].index))
        land_use = [o for o in self.plan.objects if o.required_text and o.identity not in linked]
        if land_use:
            found.append(Finding(VARNING, f"{len(land_use)} objekt med mark- och vattenanvändning är inte kopplade till "
                                          "något avsnitt. Ställningstagandet för dem behöver gå att läsa i "
                                          "planhandlingen.", _names(land_use), identity=land_use[0].identity))
        plan = self.plan.plan_object()
        if plan is not None and plan.identity not in linked:
            found.append(Finding(INFO, "Inget avsnitt är kopplat till hela planen (till exempel syftet eller "
                                       "sammanfattningen).", "Hela planen"))
        other = [o for o in self.plan.objects
                 if o.kind != PLAN_KIND and not o.required_text and o.identity not in linked]
        if other:
            found.append(Finding(INFO, f"{len(other)} objekt med annat innehåll är inte kopplade till något avsnitt.",
                                 _names(other), identity=other[0].identity))
        lonely = [s for s in tagged if not self.links[s.index] and s.text]
        if lonely:
            found.append(Finding(INFO, f"{len(lonely)} avsnitt får bokmärken men är inte kopplade till något i planen. "
                                       "Det går bra för text som inte handlar om ett visst innehåll.",
                                 lonely[0].heading, section=lonely[0].index))
        return found

    # -- spara ----------------------------------------------------------------------------------------------------------
    def to_save(self, names: dict[int, str]) -> list[SectionToSave]:
        return [SectionToSave(names[s.index], s.heading, self.types[s.index], set(self.links[s.index]))
                for s in self.sections if s.index in names]

    def default_destination(self) -> Path:
        return ph.bookmarked_copy_name(self.docx)

    def save(self, destination: str | Path, web: bool = False) -> str:
        """Skriver kopian med bokmärken och sparar kopplingarna i planen; med ``web`` också en webbversion (HTML) bredvid
        kopian. Programmet arbetar sedan vidare i kopian."""
        if not self.ready:
            raise SessionError("Välj planhandling först.")
        destination = Path(destination)
        names = ph.bookmark_names(self.document, {s.index for s in self.tagged()})
        sections = self.to_save(names)
        try:
            ph.write(self.document, destination, names)
            self.host.save(destination, sections)
            document = ph.read(destination, self.plan.types)
        except (ph.DocxError, ValueError, OSError) as exc:
            raise SessionError(f"Kunde inte spara: {exc}") from exc
        if len(document.sections) == len(self.document.sections):
            self.document, self.docx = document, destination  # samma avsnitt: arbeta vidare i kopian
            self.saved_from = {s.index for s in document.sections if s.bookmark}
            self.reviewed |= self.saved_from
        self.dirty = False
        self.saved_to = destination
        self.store.put(self.recent_key(), str(destination))
        linked = sum(1 for s in sections if s.identities)
        rows = sum(len(s.identities) for s in sections)
        message = (f"Sparade {destination.name}: {len(sections)} avsnitt med bokmärken, {linked} kopplade till planen "
                   f"({rows} {'rad' if rows == 1 else 'rader'} i dokumentavsnitt).")
        if web:
            try:
                page = self.save_web(destination, {s.bookmark: s.type for s in sections})
                message += f" Webbversionen är {page.name}."
            except SessionError as exc:  # kopian och kopplingarna är sparade ändå
                message += f" {exc}"
        return message

    def save_web(self, docx: Path, types: Optional[dict[str, str]] = None) -> Path:
        """Webbversionen (HTML) av en planhandling med bokmärken, bredvid den: ``<namn>.html``."""
        try:
            return ph_html.write(docx, ph_html.html_name(docx), types, self.plan.title if self.plan else "")
        except (ph.DocxError, OSError, SyntaxError) as exc:  # SyntaxError: XML som inte går att läsa
            raise SessionError(f"Webbversionen kunde inte sparas: {exc}") from exc

    def overview_rows(self) -> list[tuple[str, str, str, str]]:
        """(bokmärke, rubrik, avsnittstyp, objekt) per koppling, för förhandsvisningen och CSV-filen. Bokmärken som
        inte är skapade än visas som "(nytt)"."""
        rows = []
        for section in self.tagged():
            name = section.bookmark or "(nytt)"
            objects = sorted(self.links[section.index], key=lambda i: self._object_title(i))
            if not objects:
                rows.append((name, section.heading, self.types[section.index], ""))
            for identity in objects:
                rows.append((name, section.heading, self.types[section.index], self._object_title(identity)))
        return rows

    def _object_title(self, identity: str) -> str:
        obj = self.plan.object(identity) if self.plan else None
        return obj.long_title() if obj else f"saknas i planen ({identity[:8]}…)"
