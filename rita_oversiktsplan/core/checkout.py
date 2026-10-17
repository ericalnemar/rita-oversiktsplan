"""Checka ut och checka in en översiktsplan som ligger i PostGIS (som i Rita Detaljplan).

Att rita direkt mot en databas över nätet blir segt, och två som ritar samtidigt skulle skriva över varandra. Därför:

* En plan som öppnas från databasen är **skrivskyddad**.
* **Checka ut** låser planen i databasen (en rad ``checkout`` i planens metadatatabell), kopierar alla planens
  tabeller till en lokal GeoPackage och pekar om planens lager dit. Ritandet går sedan lika snabbt som mot en fil.
* **Checka in** skriver tillbaka planen i en enda transaktion (allt eller inget, och bara om låset fortfarande är
  ditt), släpper låset, pekar lagren mot databasen igen och tar bort den lokala kopian.
* **Kasta utcheckningen** släpper låset och tar bort kopian utan att skriva något till databasen.

Låset är JSON (nyckel, vem, dator, sedan när). Den lokala kopian har samma nyckel i sin metadata, så en utcheckning
som avbröts (kraschad QGIS, avstängd dator) kan tas upp igen. Var planen ligger sparas på planens grupp i
lagerpanelen (och därmed i projektfilen)."""
from __future__ import annotations

import getpass
import json
import platform
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from qgis.core import QgsApplication, QgsDataProvider, QgsFeature, QgsVectorLayer

from . import geopackage, model, storage
from .project import CHECKOUT_PATH_PROPERTY as PATH_PROPERTY
from .project import CHECKOUT_TOKEN_PROPERTY as TOKEN_PROPERTY
from .project import PLAN_PROPERTY, TABLE_PROPERTY, hide_plan_column
from .storage import PostgisError, PostgisStorage, literal

LOCK_KEY = "checkout"
LOCAL_KEYS = ("checkout_token", "checkout_storage", "checkout_since")
DATABASE, LOCAL, FILE = "database", "local", "file"  # var planen ligger just nu


class CheckoutError(RuntimeError):
    """Något gick fel vid utcheckning eller incheckning. Meddelandet är avsett för användaren."""


@dataclass(frozen=True)
class Lock:
    token: str
    user: str
    host: str
    since: str

    def describe(self) -> str:
        return f"{self.user} på {self.host} sedan {self.since.replace('T', ' ')}"

    def to_json(self) -> str:
        return json.dumps({"token": self.token, "user": self.user, "host": self.host, "since": self.since})

    @classmethod
    def from_json(cls, text: str) -> Optional["Lock"]:
        try:
            data = json.loads(text)
            return cls(str(data["token"]), str(data.get("user", "")), str(data.get("host", "")),
                       str(data.get("since", "")))
        except (ValueError, KeyError, TypeError):
            return None


class LockedError(CheckoutError):
    """Planen är redan utcheckad av någon annan (eller av dig på en annan dator)."""

    def __init__(self, lock: Optional[Lock]):
        self.lock = lock
        who = lock.describe() if lock is not None else "någon annan"
        super().__init__(f"Planen är utcheckad av {who}. Bara en kan redigera planen åt gången.")


# -- låset i databasen -------------------------------------------------------------------------------------------------
def _token_pattern(token: str) -> str:
    """LIKE-mönster som hittar låsraden med nyckeln (ingen JSON-tolkning: andra rader i tabellen är inte JSON)."""
    if not token.isalnum():
        raise ValueError("ogiltig låsnyckel")
    return literal(f'%"token": "{token}"%')


def read_lock(plan: PostgisStorage) -> Optional[Lock]:
    text = plan.read_meta().get(LOCK_KEY)
    return Lock.from_json(text) if text else None


def new_lock() -> Lock:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - saknas i vissa tjänstemiljöer
        user = "okänd"
    return Lock(uuid.uuid4().hex, user, platform.node() or "okänd dator", datetime.now().isoformat(timespec="seconds"))


def acquire_lock(plan: PostgisStorage) -> Lock:
    """Låser planen. Kastar ``LockedError`` om den redan är låst. Metadatatabellen låses kort medan raden läggs in, så
    att två som checkar ut samtidigt inte båda får låset."""
    lock = new_lock()
    meta = plan.table(model.META_TABLE)
    plan_id = literal(plan.plan_id)
    plan.sql(storage.transaction_sql([
        f"LOCK TABLE {meta} IN EXCLUSIVE MODE;",
        f"IF NOT EXISTS (SELECT 1 FROM {meta} WHERE \"plan\" = {plan_id} AND \"key\" = {literal(LOCK_KEY)}) THEN "
        f"INSERT INTO {meta} (\"plan\", \"key\", \"value\") VALUES ({plan_id}, {literal(LOCK_KEY)}, "
        f"{literal(lock.to_json())}); END IF;"]))
    current = read_lock(plan)
    if current is None or current.token != lock.token:
        raise LockedError(current)
    return lock


def release_lock(plan: PostgisStorage, token: str) -> None:
    """Släpper låset om det fortfarande är ditt."""
    plan.sql(f"DELETE FROM {plan.table(model.META_TABLE)} WHERE \"plan\" = {literal(plan.plan_id)} "
             f"AND \"key\" = {literal(LOCK_KEY)} AND \"value\" LIKE {_token_pattern(token)}")


def break_lock(plan: PostgisStorage) -> None:
    """Tar bort låset oavsett vems det är. Den som hade planen utcheckad kan då inte checka in den."""
    plan.sql(f"DELETE FROM {plan.table(model.META_TABLE)} WHERE \"plan\" = {literal(plan.plan_id)} "
             f"AND \"key\" = {literal(LOCK_KEY)}")


# -- var planen ligger -------------------------------------------------------------------------------------------------
def db_storage(group) -> Optional[PostgisStorage]:
    key = group.customProperty(PLAN_PROPERTY) or ""
    return PostgisStorage.from_key(key) if key.startswith(storage.KEY_PREFIX) else None


def local_path(group) -> Optional[Path]:
    text = group.customProperty(PATH_PROPERTY)
    return Path(text) if text else None


def state(group) -> str:
    """``DATABASE`` (läses direkt från databasen, skrivskyddad), ``LOCAL`` (utcheckad) eller ``FILE`` (GeoPackage)."""
    if db_storage(group) is None:
        return FILE
    return LOCAL if local_path(group) is not None and group.customProperty(TOKEN_PROPERTY) else DATABASE


def checkouts_dir() -> Path:
    return Path(QgsApplication.qgisSettingsDirPath()) / "rita_oversiktsplan" / "checkouts"


def copy_path(plan: PostgisStorage, lock: Lock, directory: Optional[Path] = None) -> Path:
    name = f"{plan.connection_name}_{plan.schema}_{plan.plan_id}_{lock.token[:8]}.gpkg"
    return (directory or checkouts_dir()) / "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


# -- lagren: peka om mellan databasen och den lokala kopian ------------------------------------------------------------
def _plan_layers(group) -> list[tuple[QgsVectorLayer, model.LayerDef]]:
    found = []
    for node in group.findLayers():
        layer = node.layer()
        table = layer.customProperty(TABLE_PROPERTY) if layer is not None else None
        if table:
            found.append((layer, model.layer(table)))
    return found


def is_editing(group) -> bool:
    return any(layer.isEditable() for layer, _ in _plan_layers(group))


def _switch(group, target: storage.Storage) -> None:
    """Pekar om alla planens lager. Lagren behåller sina id, sin stil och sina formulär."""
    if is_editing(group):
        raise CheckoutError("Avsluta redigeringen (spara eller kasta ändringarna) först.")
    for layer, layer_def in _plan_layers(group):
        uri, provider = target.layer_source(layer_def)
        layer.setReadOnly(False)
        layer.setDataSource(uri, layer.name(), provider, QgsDataProvider.ProviderOptions())
        if not layer.isValid():
            raise CheckoutError(f"Kunde inte öppna tabellen {layer_def.name} på den nya platsen.")
        layer.setReadOnly(target.read_only)
        hide_plan_column(layer)
        layer.triggerRepaint()


def enforce_read_only(group) -> None:
    """En plan som läses direkt från databasen är skrivskyddad."""
    if state(group) == DATABASE:
        for layer, _ in _plan_layers(group):
            if not layer.isEditable():
                layer.setReadOnly(True)


# -- kopiera ---------------------------------------------------------------------------------------------------------
def _copy_rows(source: QgsVectorLayer, target: QgsVectorLayer, skip=None) -> int:
    fields = target.fields()
    positions = [(index, source.fields().indexOf(field.name())) for index, field in enumerate(fields)
                 if field.name() != "fid"]
    features = []
    for old in source.getFeatures():
        if skip is not None and skip(old):
            continue
        new = QgsFeature(fields)
        if old.hasGeometry():
            new.setGeometry(old.geometry())
        for target_index, source_index in positions:
            if source_index >= 0:
                new.setAttribute(target_index, old.attribute(source_index))
        features.append(new)
    if features:
        ok, _ = target.dataProvider().addFeatures(features)
        if not ok:
            raise CheckoutError(f"Kunde inte skriva tabellen {target.name()} i den lokala kopian.")
    return len(features)


def download(plan: PostgisStorage, path: Path, lock: Lock) -> Path:
    """Kopierar planens alla tabeller (även ÖP-katalogens värden och metadatan) från databasen till en ny GeoPackage."""
    path.parent.mkdir(parents=True, exist_ok=True)
    geopackage.create_geopackage(path, None, epsg=plan.epsg)
    local = storage.GeoPackageStorage(path)
    for table in storage.tables():
        source = QgsVectorLayer(plan.layer_uri(table), table.name, storage.PROVIDER)
        if not source.isValid():
            raise CheckoutError(f"Kunde inte läsa tabellen {table.name} i databasen.")
        target = QgsVectorLayer(local.layer_source(table)[0], table.name, "ogr")
        skip = (lambda f: f["key"] == LOCK_KEY) if table.name == model.META_TABLE else None
        _copy_rows(source, target, skip)
    local.write_meta({"checkout_token": lock.token, "checkout_storage": plan.key, "checkout_since": lock.since})
    return path


def local_copies(plan: PostgisStorage, directory: Optional[Path] = None) -> list[tuple[Path, dict]]:
    """Lokala kopior på den här datorn som hör till planen, med sin metadata."""
    found = []
    folder = directory or checkouts_dir()
    for path in sorted(folder.glob("*.gpkg")) if folder.exists() else []:
        meta = geopackage.read_meta(path)
        if meta.get("checkout_storage") == plan.key:
            found.append((path, meta))
    return found


def resumable_copy(plan: PostgisStorage, directory: Optional[Path] = None) -> Optional[tuple[Path, Lock]]:
    """En avbruten utcheckning som går att fortsätta: en lokal kopia vars lås fortfarande är ditt."""
    lock = read_lock(plan)
    if lock is None:
        return None
    for path, meta in local_copies(plan, directory):
        if meta.get("checkout_token") == lock.token:
            return path, lock
    return None


def _remember(group, path: Optional[Path], token: str) -> None:
    group.setCustomProperty(PATH_PROPERTY, str(path) if path else "")
    group.setCustomProperty(TOKEN_PROPERTY, token)


def _remove(path: Path) -> bool:
    """Tar bort kopian (och SQLites hjälpfiler). Returnerar False om något inte gick att ta bort."""
    clean = True
    for suffix in ("", "-wal", "-shm", "-journal"):
        target = Path(str(path) + suffix)
        try:
            if target.exists():
                target.unlink()
        except OSError:
            clean = False
    return clean


# -- checka ut och in --------------------------------------------------------------------------------------------------
def check_out(group, directory: Optional[Path] = None) -> Path:
    """Låser planen och gör en lokal kopia som planens lager pekar mot. Returnerar kopians sökväg."""
    plan = db_storage(group)
    if plan is None or state(group) != DATABASE:
        raise CheckoutError("Planen ligger inte i en databas, eller är redan utcheckad.")
    if is_editing(group):
        raise CheckoutError("Avsluta redigeringen (spara eller kasta ändringarna) först.")
    try:
        lock = acquire_lock(plan)
    except PostgisError as exc:
        raise CheckoutError(str(exc)) from exc
    path = copy_path(plan, lock, directory)
    try:
        download(plan, path, lock)
        _switch(group, storage.GeoPackageStorage(path))
    except Exception as exc:
        try:
            _switch(group, plan)
        except Exception:  # noqa: BLE001 - städningen får inte dölja det ursprungliga felet
            pass
        try:
            release_lock(plan, lock.token)
        except Exception:  # noqa: BLE001
            pass
        _remove(path)
        if isinstance(exc, (CheckoutError, PostgisError)):
            raise CheckoutError(f"Kunde inte checka ut planen: {exc}") from exc
        raise
    _remember(group, path, lock.token)
    return path


def resume(group, path: Path, lock: Lock) -> Path:
    """Tar upp en avbruten utcheckning: pekar lagren mot den lokala kopian igen."""
    _switch(group, storage.GeoPackageStorage(path))
    _remember(group, path, lock.token)
    return path


def check_in_sql(plan: PostgisStorage, token: str, path: Path) -> str:
    """Ett SQL-block som i en transaktion kontrollerar att låset är ditt, ersätter planens rader (geometri- och
    attributtabellerna och metadatan, inte ÖP-katalogens värden som inte ändras) med den lokala kopians, och släpper
    låset. Går något fel rullas allt tillbaka."""
    meta = plan.table(model.META_TABLE)
    plan_id = literal(plan.plan_id)
    epsg = storage.GeoPackageStorage(path).epsg
    parts = [f"IF NOT EXISTS (SELECT 1 FROM {meta} WHERE \"plan\" = {plan_id} AND \"key\" = {literal(LOCK_KEY)} "
             f"AND \"value\" LIKE {_token_pattern(token)}) THEN "
             "RAISE EXCEPTION 'Låset på planen tillhör inte längre dig. Planen har inte checkats in.'; END IF;"]
    for table in storage.tables():
        if table.name in {lookup.name for lookup in model.LOOKUPS}:
            continue
        rows = storage.read_file_rows(path, table)
        keep = ""
        if table.name == model.META_TABLE:
            rows = [r for r in rows if r.get("key") not in LOCAL_KEYS and r.get("key") != LOCK_KEY]
            keep = f"\"key\" = {literal(LOCK_KEY)}"
        parts += storage.replace_rows_sql(plan.schema, plan.plan_id, table, rows, keep, epsg)
    parts.append(f"DELETE FROM {meta} WHERE \"plan\" = {plan_id} AND \"key\" = {literal(LOCK_KEY)};")
    return storage.transaction_sql(parts)


def check_in(group) -> tuple[Path, bool]:
    """Skriver planen till databasen, släpper låset, pekar tillbaka lagren och tar bort den lokala kopian. Returnerar
    kopians sökväg och om den gick att ta bort. Vid fel ändras ingenting: låset och kopian finns kvar."""
    plan, path, token = db_storage(group), local_path(group), group.customProperty(TOKEN_PROPERTY)
    if plan is None or state(group) != LOCAL:
        raise CheckoutError("Planen är inte utcheckad.")
    if is_editing(group):
        raise CheckoutError("Avsluta redigeringen (spara eller kasta ändringarna) först.")
    try:
        plan.sql(check_in_sql(plan, token, path))
    except PostgisError as exc:
        raise CheckoutError(f"Kunde inte checka in planen: {exc}") from exc
    _switch(group, plan)
    _remember(group, None, "")
    return path, _remove(path)


def discard(group) -> tuple[Path, bool]:
    """Släpper låset och tar bort den lokala kopian utan att skriva något till databasen."""
    plan, path, token = db_storage(group), local_path(group), group.customProperty(TOKEN_PROPERTY)
    if plan is None or state(group) != LOCAL:
        raise CheckoutError("Planen är inte utcheckad.")
    if is_editing(group):
        raise CheckoutError("Avsluta redigeringen (spara eller kasta ändringarna) först.")
    try:
        release_lock(plan, token)
    except PostgisError as exc:
        raise CheckoutError(f"Kunde inte släppa låset i databasen: {exc}") from exc
    _switch(group, plan)
    _remember(group, None, "")
    return path, _remove(path)
