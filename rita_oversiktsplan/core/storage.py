"""Var planen lagras: en GeoPackage-fil eller ett schema i en PostGIS-databas (som i Rita Detaljplan).

Båda har samma tabeller (se :mod:`model`). Resten av pluginet läser planen genom ``Storage`` och behöver inte veta
vilket det är. Ett PostGIS-schema delas av alla planer som lagts i det: varje tabell har en kolumn ``plan`` som
skiljer planernas rader åt, och varje QGIS-lager är tabellen filtrerad på just den planens identifierare. Även
uppslagstabellerna med ÖP-katalogens värden och metadatatabellen har kolumnen, så att varje plan behåller sin egen
katalogversion. Databasanslutningen är en av QGIS sparade PostgreSQL-anslutningar, så inloggningen sköts av QGIS.

Man ritar aldrig direkt mot databasen: en plan som öppnas därifrån är skrivskyddad och checkas ut till en lokal
GeoPackage för att redigeras (se :mod:`checkout`)."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Optional

from qgis.core import Qgis, QgsDataSourceUri, QgsProviderRegistry, QgsVectorLayer

from . import geopackage, model

PROVIDER = "postgres"
SCHEMA_TABLE = "rita_oversiktsplan_schema"  # schemats egna nycklar (schemaversion), gemensamma för alla planer
KEY_PREFIX = "postgis:"
BATCH = 200  # rader per INSERT
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_TRANSLITERATE = str.maketrans({"å": "a", "ä": "a", "ö": "o", "é": "e", "ü": "u"})
_SQL_TYPES = {model.TEXT: "text", model.INT: "integer", model.REAL: "double precision", model.DATE: "date",
              model.DATETIME: "timestamp", model.BOOL: "boolean"}
_WKB = {"MultiPolygon": Qgis.WkbType.MultiPolygon, "MultiLineString": Qgis.WkbType.MultiLineString,
        "Point": Qgis.WkbType.Point}


MAX_IDENTIFIER = 63  # PostgreSQL kortar längre namn (i byte), så att olika tabeller kan få samma namn
# Boverkets tabellnamn som är för långa för PostgreSQL får ett kortare namn i databasen (i GeoPackage behålls mallens)
SHORT_NAMES = {"sarskiltvardefullabyggnadsverkallmannaplatserochbebyggelseomraden": "sarskiltvardefullkulturmiljo"}


def db_name(name: str) -> str:
    """Tabellens namn i databasen: samma som i GeoPackage, utom när det är längre än PostgreSQL tillåter. Då kortas
    det läsbart (``SHORT_NAMES``) eller, om det inte räcker, med en kort kontrollsumma på slutet."""
    if len(name.encode("utf-8")) <= MAX_IDENTIFIER:
        return name
    for long, short in SHORT_NAMES.items():
        name = name.replace(long, short)
    if len(name.encode("utf-8")) <= MAX_IDENTIFIER:
        return name
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    head = name.encode("utf-8")[:MAX_IDENTIFIER - 9].decode("utf-8", "ignore")
    return f"{head}_{digest}"


def index_name(table: str, column: str) -> str:
    """Ett kort, unikt indexnamn (index syns inte för användaren)."""
    return f"rop_{hashlib.sha1(table.encode('utf-8')).hexdigest()[:12]}_{column}"


def _short_error(text: str) -> str:
    """Databasens eget felmeddelande, utan den långa SQL-frågan som QGIS lägger före."""
    match = re.search(r"ERROR:\s*(.+?)(?:\n|$)", text)
    return match.group(1).strip() if match else text[:500]


class PostgisError(RuntimeError):
    """Något gick fel mot databasen. Meddelandet är avsett för användaren."""


def _execute(connection, sql: str):
    try:
        return connection.executeSql(sql)
    except PostgisError:
        raise
    except Exception as exc:  # QgsProviderConnectionException m.fl.
        raise PostgisError(f"Databasen svarade med ett fel: {_short_error(str(exc))}") from exc


# -- tabellerna i en plan (samma i filen och i databasen) ----------------------------------------------------------
class Table:
    """En tabell som flyttas mellan filen och databasen: namn, geometri och kolumner (namn, typ)."""

    def __init__(self, name: str, geometry: Optional[str], columns: list[tuple[str, str]]):
        self.name, self.geometry, self.columns = name, geometry, columns


def tables() -> list[Table]:
    """Planens geometri- och attributtabeller, uppslagstabellerna och metadatatabellen."""
    result = [Table(d.name, d.geometry, [(f.name, f.type) for f in d.fields]) for d in model.LAYERS]
    for lookup in model.LOOKUPS:
        result.append(Table(lookup.name, None, [(c, model.TEXT) for c in geopackage.lookup_columns(lookup)]))
    result.append(Table(model.META_TABLE, None, [("key", model.TEXT), ("value", model.TEXT)]))
    return result


# -- namn och SQL (rena funktioner) -----------------------------------------------------------------------------------
def identifier(text: str) -> str:
    """Gör fri text (till exempel planens titel) till ett giltigt schema- eller plan-id: gemener a–z, siffror och
    understreck, börjar med en bokstav."""
    name = re.sub(r"[^a-z0-9_]+", "_", (text or "").strip().lower().translate(_TRANSLITERATE)).strip("_")
    if name and not name[0].isalpha():
        name = "op_" + name
    return name[:63]


def is_valid_schema(name: str) -> bool:
    return bool(_IDENTIFIER_RE.match(name or "")) and name not in ("public", "information_schema") \
        and not name.startswith("pg_")


def is_valid_plan_id(name: str) -> bool:
    return bool(_IDENTIFIER_RE.match(name or ""))


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def literal(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def ensure_schema_sql(schema: str, epsg: int = model.EPSG) -> list[str]:
    """SQL som skapar schemat med alla tabeller, om de inte redan finns (en ny plan i ett befintligt schema lägger
    bara till sina rader)."""
    statements = [f"CREATE SCHEMA IF NOT EXISTS {quote(schema)}",
                  f'CREATE TABLE IF NOT EXISTS {quote(schema)}.{quote(SCHEMA_TABLE)} ("key" text PRIMARY KEY, '
                  '"value" text)']
    for table in tables():
        name = f"{quote(schema)}.{quote(db_name(table.name))}"
        columns = ['"fid" serial PRIMARY KEY', '"plan" text NOT NULL']
        if table.geometry:
            columns.append(f'"geom" geometry({table.geometry}, {int(epsg)})')
        columns += [f"{quote(column)} {_SQL_TYPES[kind]}" for column, kind in table.columns]
        statements.append(f"CREATE TABLE IF NOT EXISTS {name} ({', '.join(columns)})")
        statements.append(f"CREATE INDEX IF NOT EXISTS {quote(index_name(table.name, 'plan'))} ON {name} "
                          '("plan")')
        if table.geometry:
            statements.append(f"CREATE INDEX IF NOT EXISTS {quote(index_name(table.name, 'geom'))} ON {name} "
                              'USING gist ("geom")')
    statements.append(f"CREATE UNIQUE INDEX IF NOT EXISTS {quote(index_name(model.META_TABLE, 'plan_key'))} ON "
                      f'{quote(schema)}.{quote(model.META_TABLE)} ("plan", "key")')
    return statements + added_columns_sql(schema)


def added_columns_sql(schema: str) -> list[str]:
    """Kolumner som kommit till i senare schemaversioner, för scheman som skapats tidigare (``CREATE TABLE IF NOT
    EXISTS`` lägger inte till kolumner i en befintlig tabell)."""
    statements = []
    for table, columns in model.ADDED_COLUMNS.items():
        kinds = {f.name: f.type for f in model.layer(table).fields}
        for column in columns:
            statements.append(f"ALTER TABLE {quote(schema)}.{quote(db_name(table))} ADD COLUMN IF NOT EXISTS "
                              f"{quote(column)} {_SQL_TYPES[kinds[column]]}")
    return statements


UPGRADABLE = ("3",)  # schemaversioner i databasen som pluginet kan uppgradera


def upgrade_schema_sql(schema: str, epsg: int) -> str:
    """Uppgraderar ett schema i databasen till pluginets schemaversion: saknade tabeller och kolumner läggs till, och
    alla planer i schemat (de delar tabeller) får den nya versionen. En transaktion."""
    version = literal(model.SCHEMA_VERSION)
    parts = [statement + ";" for statement in ensure_schema_sql(schema, epsg)]
    parts.append(f'UPDATE {quote(schema)}.{quote(model.META_TABLE)} SET "value" = {version} '
                 "WHERE \"key\" = 'schema_version';")
    parts.append(f'UPDATE {quote(schema)}.{quote(SCHEMA_TABLE)} SET "value" = {version} WHERE "key" = '
                 "'schema_version';")
    return transaction_sql(parts)


def sql_value(value, kind: str) -> str:
    """En cell som SQL-värde för kolumntypen ``kind`` (se :mod:`model`)."""
    import datetime

    from qgis.core import NULL
    from qgis.PyQt.QtCore import QDate, QDateTime
    if value is None or value == NULL or (hasattr(value, "isNull") and value.isNull()):
        return "NULL"
    if kind == model.BOOL:
        return "true" if value in (True, 1, "1", "true", "True") else "false"
    if kind == model.INT:
        return str(int(value))
    if kind == model.REAL:
        return repr(float(value))
    if isinstance(value, QDateTime):
        return literal(value.toString("yyyy-MM-dd HH:mm:ss")) if value.isValid() else "NULL"
    if isinstance(value, QDate):
        return literal(value.toString("yyyy-MM-dd")) if value.isValid() else "NULL"
    if isinstance(value, datetime.datetime):
        return literal(value.strftime("%Y-%m-%d %H:%M:%S"))
    if isinstance(value, datetime.date):
        return literal(value.isoformat())
    return literal(value)


def replace_rows_sql(schema: str, plan_id: str, table: Table, rows: list[dict], keep: str = "",
                     epsg: int = model.EPSG) -> list[str]:
    """Tar bort planens rader i tabellen och lägger in ``rows`` (``{kolumn: värde}``, geometrin som WKT i ``geom``).
    Andra planers rader rörs inte. ``fid`` sätts inte: databasen ger nya, eftersom den lokala kopians fid börjar om
    på 1 och skulle krocka med andra planers rader; kopplingarna i planen går via objektidentitet, inte fid. ``keep``
    är ett extra villkor för rader som ska vara kvar (låset i metadatatabellen)."""
    name = f"{quote(schema)}.{quote(db_name(table.name))}"
    plan = literal(plan_id)
    parts = [f"DELETE FROM {name} WHERE \"plan\" = {plan}{' AND NOT (' + keep + ')' if keep else ''};"]
    columns = ["plan"] + (["geom"] if table.geometry else []) + [column for column, _ in table.columns]
    column_list = ", ".join(quote(c) for c in columns)
    for start in range(0, len(rows), BATCH):
        values = []
        for row in rows[start:start + BATCH]:
            cells = [plan]
            if table.geometry:
                wkt = row.get("geom")
                geometry = f"ST_GeomFromText({literal(wkt)}, {int(epsg)})"
                if wkt is not None and table.geometry.startswith("Multi"):
                    geometry = f"ST_Multi({geometry})"
                cells.append("NULL" if wkt is None else geometry)
            cells += [sql_value(row.get(column), kind) for column, kind in table.columns]
            values.append("(" + ", ".join(cells) + ")")
        parts.append(f"INSERT INTO {name} ({column_list}) VALUES {', '.join(values)};")
    return parts


def transaction_sql(parts: list[str]) -> str:
    """Ett ``DO``-block: allt körs i en transaktion, och går något fel rullas allt tillbaka."""
    body = " ".join(parts)
    tag, n = "op", 0
    while f"${tag}$" in body:  # dollarcitatet får inte förekomma i innehållet
        n += 1
        tag = f"op{n}"
    return f"DO ${tag}$ BEGIN {body} END ${tag}$"


def read_file_rows(path: Path, table: Table) -> list[dict]:
    """Raderna i en tabell i en GeoPackage: ``{kolumn: värde}`` och geometrin som WKT i ``geom``."""
    layer = QgsVectorLayer(f"{path.as_posix()}|layername={table.name}", table.name, "ogr")
    if not layer.isValid():
        raise PostgisError(f"Kunde inte läsa tabellen {table.name} i {path.name}.")
    rows = []
    for feature in layer.getFeatures():
        row = {}
        if table.geometry:
            geometry = feature.geometry()
            row["geom"] = None if geometry is None or geometry.isNull() or geometry.isEmpty() else geometry.asWkt(6)
        for column, _ in table.columns:
            row[column] = feature.attribute(column) if layer.fields().indexOf(column) >= 0 else None
        rows.append(row)
    return rows


# -- lagringssätt ---------------------------------------------------------------------------------------------------
class Storage:
    """Där en plans tabeller finns."""
    kind = ""
    read_only = False

    @property
    def key(self) -> str:  # sparas på planens grupp i lagerpanelen
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def read_meta(self) -> dict[str, str]:
        raise NotImplementedError

    def write_meta(self, values: dict[str, str]) -> None:
        raise NotImplementedError

    def read_defaults(self) -> dict[str, str]:
        meta = self.read_meta()
        return {field: meta.get(key, model.DEFAULT_VALUES[key]) for field, key in model.DEFAULT_KEYS.items()}

    def write_defaults(self, defaults: dict[str, str]) -> None:
        self.write_meta({model.DEFAULT_KEYS[field]: value for field, value in defaults.items()})

    def read_lookup(self, lookup: model.LookupDef) -> list[str]:
        raise NotImplementedError

    @property
    def epsg(self) -> int:
        """Planens koordinatsystem (SWEREF 99 TM om metadatan inte säger annat)."""
        value = self.read_meta().get("epsg", "")
        return int(value) if value.isdigit() else model.EPSG

    def read_lookup_values(self, lookup: model.LookupDef) -> dict[str, dict[str, str]]:
        raise NotImplementedError

    def layer_source(self, layer_def: model.LayerDef) -> tuple[str, str]:
        """(adress, dataleverantör) för ett lager."""
        raise NotImplementedError


class GeoPackageStorage(Storage):
    kind = "geopackage"

    def __init__(self, path):
        self.path = Path(path)

    @property
    def key(self) -> str:
        return str(self.path)

    @property
    def name(self) -> str:
        return self.path.stem

    def describe(self) -> str:
        return self.path.name

    def read_meta(self) -> dict[str, str]:
        return geopackage.read_meta(self.path)

    def write_meta(self, values: dict[str, str]) -> None:
        geopackage.write_meta(self.path, values)

    def read_lookup(self, lookup: model.LookupDef) -> list[str]:
        return geopackage.read_lookup(self.path, lookup)

    def read_lookup_values(self, lookup: model.LookupDef) -> dict[str, dict[str, str]]:
        return geopackage.read_lookup_values(self.path, lookup)

    def layer_source(self, layer_def: model.LayerDef) -> tuple[str, str]:
        return f"{self.path.as_posix()}|layername={layer_def.name}", "ogr"

    def __eq__(self, other):
        return isinstance(other, GeoPackageStorage) and other.path == self.path

    def __hash__(self):
        return hash(self.path)


def postgis_connections() -> dict:
    """QGIS sparade PostgreSQL-anslutningar (namn → anslutning)."""
    metadata = QgsProviderRegistry.instance().providerMetadata(PROVIDER)
    return dict(metadata.connections()) if metadata is not None else {}


class PostgisStorage(Storage):
    kind = "postgis"
    read_only = True  # ändras bara genom utcheckning

    def __init__(self, connection_name: str, schema: str, plan_id: str, connection=None):
        self.connection_name, self.schema, self.plan_id = connection_name, schema, plan_id
        self._connection = connection

    @classmethod
    def from_key(cls, key: str) -> "PostgisStorage":
        connection, schema, plan_id = json.loads(key[len(KEY_PREFIX):])
        return cls(connection, schema, plan_id)

    @property
    def key(self) -> str:
        return KEY_PREFIX + json.dumps([self.connection_name, self.schema, self.plan_id], ensure_ascii=False)

    @property
    def name(self) -> str:
        return self.plan_id

    def describe(self) -> str:
        return f"{self.connection_name} · {self.schema} · {self.plan_id}"

    @property
    def connection(self):
        if self._connection is None:
            found = postgis_connections().get(self.connection_name)
            if found is None:
                raise PostgisError(f"Databasanslutningen {self.connection_name} finns inte bland QGIS sparade "
                                   "anslutningar.")
            self._connection = found
        return self._connection

    def sql(self, statement: str):
        return _execute(self.connection, statement)

    def table(self, name: str) -> str:
        return f"{quote(self.schema)}.{quote(db_name(name))}"

    def read_meta(self) -> dict[str, str]:
        try:
            rows = self.sql(f'SELECT "key", "value" FROM {self.table(model.META_TABLE)} '
                            f'WHERE "plan" = {literal(self.plan_id)}')
        except PostgisError:
            return {}
        return {row[0]: row[1] for row in rows}

    def write_meta(self, values: dict[str, str]) -> None:
        raise PostgisError("Planen ligger i databasen och är skrivskyddad. Checka ut den först.")

    def upgrade(self) -> bool:
        """Uppgraderar schemat om planen är skapad med en äldre version av pluginet. Returnerar True om något
        ändrades. Kräver rätt att ändra tabellerna i schemat."""
        if self.read_meta().get("schema_version") not in UPGRADABLE:
            return False
        try:
            self.sql(upgrade_schema_sql(self.schema, self.epsg))
        except PostgisError as exc:
            raise PostgisError(f"Schemat {self.schema} är skapat med en äldre version av pluginet och behöver "
                               "uppgraderas (en kolumn läggs till), men det gick inte. Den som har rätt att ändra "
                               f"tabellerna i schemat behöver öppna en plan i det en gång. {exc}") from exc
        return True

    def read_lookup(self, lookup: model.LookupDef) -> list[str]:
        rows = self.sql(f'SELECT {quote(lookup.value_column)} FROM {self.table(lookup.name)} '
                        f'WHERE "plan" = {literal(self.plan_id)} ORDER BY "fid"')
        return [row[0] for row in rows]

    def read_lookup_values(self, lookup: model.LookupDef) -> dict[str, dict[str, str]]:
        rows = self.sql(f'SELECT {quote(lookup.value_column)}, "vardereferens", "grupp_varde", "gruppreferens" '
                        f'FROM {self.table(lookup.name)} WHERE "plan" = {literal(self.plan_id)} ORDER BY "fid"')
        return {row[0]: {"varde": row[0], "vardereferens": row[1], "grupp": row[2], "gruppreferens": row[3]}
                for row in rows if row[0]}

    def layer_uri(self, layer_def: model.LayerDef) -> str:
        uri = QgsDataSourceUri(self.connection.uri())
        uri.setDataSource(self.schema, db_name(layer_def.name), "geom" if layer_def.geometry else "",
                          f'"plan" = {literal(self.plan_id)}', "fid")
        if layer_def.geometry:
            uri.setSrid(str(self.epsg))
            uri.setWkbType(_WKB[layer_def.geometry])
        return uri.uri(True)

    def layer_source(self, layer_def: model.LayerDef) -> tuple[str, str]:
        return self.layer_uri(layer_def), PROVIDER

    def __eq__(self, other):
        return isinstance(other, PostgisStorage) and (other.connection_name, other.schema, other.plan_id) == \
            (self.connection_name, self.schema, self.plan_id)

    def __hash__(self):
        return hash((self.connection_name, self.schema, self.plan_id))


def from_key(key: str) -> Storage:
    return PostgisStorage.from_key(key) if key.startswith(KEY_PREFIX) else GeoPackageStorage(key)


def as_storage(source) -> Storage:
    """Tar emot en sökväg (GeoPackage) eller ett ``Storage``."""
    return source if isinstance(source, Storage) else GeoPackageStorage(source)


# -- databasen --------------------------------------------------------------------------------------------------------
def list_schemas(connection) -> list[str]:
    return [row[0] for row in _execute(connection, "SELECT schema_name FROM information_schema.schemata")]


def list_plugin_schemas(connection) -> list[str]:
    """Scheman som pluginet har skapat (har tabellen med schemats nycklar)."""
    rows = _execute(connection, "SELECT table_schema FROM information_schema.tables WHERE table_name = "
                                f"{literal(SCHEMA_TABLE)} ORDER BY table_schema")
    return [row[0] for row in rows]


def list_plans(connection, schema: str) -> list[tuple[str, str]]:
    """(plan-id, titel) för planerna i ett schema."""
    rows = _execute(connection, f'SELECT DISTINCT m."plan", p."planens_titel" FROM {quote(schema)}.'
                                f'{quote(model.META_TABLE)} m LEFT JOIN {quote(schema)}.'
                                f'{quote(model.OVERSIKTSPLAN.name)} p ON p."plan" = m."plan" ORDER BY m."plan"')
    return [(row[0], row[1] or "") for row in rows]


def plan_exists(connection, schema: str, plan_id: str) -> bool:
    return bool(_execute(connection, f'SELECT 1 FROM {quote(schema)}.{quote(model.META_TABLE)} '
                                     f'WHERE "plan" = {literal(plan_id)} LIMIT 1'))


def schema_epsg(connection, schema: str) -> Optional[int]:
    """Koordinatsystemet som ett befintligt schema har (gemensamt för alla planer i det), eller None."""
    try:
        rows = _execute(connection, f'SELECT "value" FROM {quote(schema)}.{quote(SCHEMA_TABLE)} WHERE "key" = '
                                    "'epsg'")
    except PostgisError:
        return None
    return int(rows[0][0]) if rows and str(rows[0][0]).isdigit() else None


def create_postgis_plan(connection_name: str, schema: str, plan_id: str, plan: geopackage.NewPlan,
                        connection=None) -> PostgisStorage:
    """Lägger in en ny plan i ett schema i databasen. Schemat och tabellerna skapas om de inte finns. Planen byggs
    först som en tillfällig GeoPackage (med ÖP-katalogen och planens uppgifter) och skrivs sedan till databasen i en
    enda transaktion. Avbryter utan ändringar om plan-id:t redan finns i schemat."""
    if not is_valid_schema(schema):
        raise PostgisError("Schemanamnet får bara innehålla gemener a–z, siffror och understreck och måste börja med "
                           "en bokstav.")
    if not is_valid_plan_id(plan_id):
        raise PostgisError("Planens id får bara innehålla gemener a–z, siffror och understreck och måste börja med "
                           "en bokstav.")
    target = PostgisStorage(connection_name, schema, plan_id, connection)
    try:
        target.sql("SELECT postgis_version()")
    except PostgisError as exc:
        raise PostgisError("Databasen saknar PostGIS (eller anslutningen fungerar inte). Tillägget aktiveras med "
                           f"CREATE EXTENSION postgis. {exc}") from exc
    existed = schema in list_plugin_schemas(target.connection)
    if existed:  # alla planer i ett schema delar tabeller och därmed koordinatsystem
        existing = schema_epsg(target.connection, schema) or model.EPSG
        if existing != plan.epsg:
            raise PostgisError(f"Schemat {schema} har koordinatsystem EPSG:{existing}. Alla planer i samma schema "
                               f"delar koordinatsystem: välj EPSG:{existing}, eller ett annat schema.")
    schema_was_there = existed or schema in list_schemas(target.connection)  # då rör vi aldrig schemat i övrigt
    if existed and plan_exists(target.connection, schema, plan_id):
        raise PostgisError(f"Det finns redan en plan med id {plan_id} i schemat {schema}.")
    try:
        for statement in ensure_schema_sql(schema, plan.epsg):
            target.sql(statement)
        if not existed:
            target.sql(f"INSERT INTO {target.table(SCHEMA_TABLE)} (\"key\", \"value\") VALUES "
                       f"('schema_version', {literal(model.SCHEMA_VERSION)}), ('epsg', {literal(plan.epsg)}) "
                       "ON CONFLICT (\"key\") DO NOTHING")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path = geopackage.create_geopackage(Path(folder) / "ny.gpkg", plan)
            parts = []
            for table in tables():
                parts += replace_rows_sql(schema, plan_id, table, read_file_rows(path, table), epsg=plan.epsg)
        target.sql(transaction_sql(parts))
    except PostgisError:
        if not schema_was_there:  # ett halvskapat schema som vi själva skapade är värre än inget: ta bort det
            try:
                target.sql(f"DROP SCHEMA IF EXISTS {quote(schema)} CASCADE")
            except PostgisError:
                pass
        raise
    return target
