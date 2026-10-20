"""Skapar och läser översiktsplanens GeoPackage utifrån datamodellen i :mod:`model`."""
from __future__ import annotations

import datetime
import sqlite3
from contextlib import closing
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from osgeo import gdal, ogr, osr

from . import model, opkatalog

gdal.UseExceptions()

_GEOMETRY_TYPES = {
    "MultiPolygon": ogr.wkbMultiPolygon,
    "MultiLineString": ogr.wkbMultiLineString,
    "Point": ogr.wkbPoint,
    None: ogr.wkbNone,
}

_FIELD_TYPES = {
    model.TEXT: (ogr.OFTString, None),
    model.INT: (ogr.OFTInteger, None),
    model.REAL: (ogr.OFTReal, None),
    model.DATE: (ogr.OFTDate, None),
    model.DATETIME: (ogr.OFTDateTime, None),
    model.BOOL: (ogr.OFTInteger, ogr.OFSTBoolean),
}


@dataclass(frozen=True)
class NewPlan:
    """Uppgifterna som en ny översiktsplan börjar med."""
    kommunkod: str
    kommunnamn: str
    titel: str
    datum_paborjat: datetime.date
    digitalt_ursprung: bool = True
    epsg: int = model.EPSG  # planens koordinatsystem: SWEREF 99 TM eller en lokal SWEREF 99-zon
    plan_area: tuple[dict, ...] = ()  # plangeometri från början (GeoJSON i planens koordinatsystem), se kommunyta


LOOKUP_COLUMNS = ("vardereferens", "grupp_varde", "gruppreferens", "version_opkatalogen")


def lookup_columns(lookup: model.LookupDef) -> tuple[str, ...]:
    """Kolumnerna i en uppslagstabell: värdet och dess id, grupp och katalogversion."""
    return (lookup.value_column, *LOOKUP_COLUMNS)


def create_geopackage(path: str | Path, plan: Optional[NewPlan], catalog: Optional[opkatalog.Catalog] = None,
                      epsg: Optional[int] = None) -> Path:
    """Skapar en GeoPackage med alla tabeller i Boverkets modell, uppslagstabellerna ifyllda ur ÖP-katalogen och en
    rad i ``oversiktsplan`` med planens uppgifter. Utan ``plan`` blir alla tabeller tomma (för en utcheckad kopia av
    en plan i en databas, som fylls med planens rader därifrån).

    Tabellerna skapas utan NOT NULL i databasen: obligatoriska fält markeras i QGIS-formulären, så att man kan spara
    en ofärdig plan."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} finns redan")
    catalog = catalog or opkatalog.bundled()
    epsg = int(epsg or (plan.epsg if plan is not None else model.EPSG))
    if epsg not in model.EPSG_CODES:
        raise ValueError(f"EPSG:{epsg} är inte SWEREF 99 TM eller en lokal SWEREF 99-zon (EPSG:3006–3018)")

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
    try:
        for layer_def in model.LAYERS:
            _create_table(ds, layer_def, srs)
        for lookup in model.LOOKUPS:
            _create_lookup(ds, lookup, catalog if plan is not None else None)
        if plan is not None:
            _insert_plan(ds.GetLayerByName(model.OVERSIKTSPLAN.name), plan)
            if plan.plan_area:
                _insert_plan_area(ds.GetLayerByName("innehall_op_plangeometri"), plan)
        _create_meta(ds, {"schema_version": str(model.SCHEMA_VERSION), "databasmodell": model.DATABASMODELL,
                          "spec_version": model.SPEC_VERSION, "opkatalog_version": catalog.version,
                          "epsg": str(epsg), **model.DEFAULT_VALUES} if plan is not None else {})
    except Exception:
        ds = None
        path.unlink(missing_ok=True)  # ingen halvfärdig fil kvar
        raise
    finally:
        ds = None  # stänger och skriver till disk
    return path


def upgrade(path: str | Path) -> bool:
    """Lägger till det som saknas i en plan som skapats med en äldre version av pluginet. Returnerar True om filen
    ändrades. Schema 1 → 2: tabellerna för otilldelad geometri och standardvärdena för nytt innehåll; 2 → 3: tabellen
    för beslut; 3 → 4: kolumnen precisering i plangeometrin. Befintliga tabeller, kolumner och värden rörs inte."""
    meta = read_meta(path)
    if meta.get("schema_version") not in ("1", "2", "3"):
        return False
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(meta.get("epsg") or model.EPSG))
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ds = ogr.Open(str(path), 1)
    try:
        for layer_def in model.ADDED_TABLES:
            if ds.GetLayerByName(layer_def.name) is None:
                _create_table(ds, layer_def, srs)
        for table, columns in model.ADDED_COLUMNS.items():
            layer = ds.GetLayerByName(table)
            if layer is None:
                continue
            existing = {layer.GetLayerDefn().GetFieldDefn(i).GetName().lower()
                        for i in range(layer.GetLayerDefn().GetFieldCount())}
            fields = {f.name: f for f in model.layer(table).fields}
            for column in columns:
                if column.lower() not in existing:
                    layer.CreateField(_field_definition(fields[column]))
    finally:
        ds = None
    write_meta(path, {**{k: v for k, v in model.DEFAULT_VALUES.items() if k not in meta},
                      "schema_version": str(model.SCHEMA_VERSION)})
    return True


def write_meta(path: str | Path, values: dict[str, str]) -> None:
    """Skriver nycklar i pluginets metadatatabell (finns nyckeln ändras värdet)."""
    with closing(sqlite3.connect(str(path), timeout=10)) as con:
        for key, value in values.items():
            changed = con.execute(f'UPDATE "{model.META_TABLE}" SET value = ? WHERE key = ?', (value, key)).rowcount
            if not changed:
                con.execute(f'INSERT INTO "{model.META_TABLE}" (key, value) VALUES (?, ?)', (key, value))
        con.commit()


def read_defaults(path: str | Path) -> dict[str, str]:
    """Standardvärdena för nytt innehåll, per fältnamn (se ``model.DEFAULT_KEYS``)."""
    meta = read_meta(path)
    return {field: meta.get(key, model.DEFAULT_VALUES[key]) for field, key in model.DEFAULT_KEYS.items()}


def write_defaults(path: str | Path, defaults: dict[str, str]) -> None:
    write_meta(path, {model.DEFAULT_KEYS[field]: value for field, value in defaults.items()})


def _create_table(ds: ogr.DataSource, layer_def: model.LayerDef, srs: osr.SpatialReference) -> None:
    options = ["FID=fid", f"IDENTIFIER={layer_def.alias}"]
    if layer_def.geometry:
        options.append("GEOMETRY_NAME=geom")
    layer = ds.CreateLayer(layer_def.name, srs=srs if layer_def.geometry else None,
                           geom_type=_GEOMETRY_TYPES[layer_def.geometry], options=options)
    for field in layer_def.fields:
        layer.CreateField(_field_definition(field))


def _field_definition(field: model.FieldDef) -> ogr.FieldDefn:
    ogr_type, subtype = _FIELD_TYPES[field.type]
    definition = ogr.FieldDefn(field.name, ogr_type)
    if subtype is not None:
        definition.SetSubType(subtype)
    if field.length:
        definition.SetWidth(field.length)
    return definition


def _create_lookup(ds: ogr.DataSource, lookup: model.LookupDef, catalog: Optional[opkatalog.Catalog]) -> None:
    layer = ds.CreateLayer(lookup.name, geom_type=ogr.wkbNone, options=["FID=fid"])
    columns = lookup_columns(lookup)
    for column in columns:
        layer.CreateField(ogr.FieldDefn(column, ogr.OFTString))
    if catalog is None:
        return
    for value in catalog.values(lookup.category, lookup.group, lookup.itself):
        feature = ogr.Feature(layer.GetLayerDefn())
        for column, data in zip(columns, (value.varde, value.vardereferens, value.grupp, value.gruppreferens,
                                          catalog.version)):
            feature.SetField(column, data)
        layer.CreateFeature(feature)


def _insert_plan(layer: ogr.Layer, plan: NewPlan) -> None:
    feature = ogr.Feature(layer.GetLayerDefn())
    now = datetime.datetime.now()
    feature.SetField("objektidentitet", str(uuid.uuid4()))
    feature.SetField("versiongiltigfran", now.year, now.month, now.day, now.hour, now.minute, now.second, 0)
    feature.SetField("kommunkod", plan.kommunkod)
    feature.SetField("kommunnamn", plan.kommunnamn)
    feature.SetField("planens_titel", plan.titel)
    d = plan.datum_paborjat
    feature.SetField("datum_paborjat", d.year, d.month, d.day, 0, 0, 0, 0)
    feature.SetField("digitalt_ursprung", 1 if plan.digitalt_ursprung else 0)
    layer.CreateFeature(feature)


def _insert_plan_area(layer: ogr.Layer, plan: NewPlan) -> None:
    """Plangeometrin som planen börjar med (kommunens yta), med samma värden som innehåll som tilldelas i QGIS."""
    import json
    now = datetime.datetime.now()
    d = plan.datum_paborjat
    for shape in plan.plan_area:
        geometry = ogr.CreateGeometryFromJson(json.dumps(shape))
        if geometry is None or geometry.IsEmpty():
            continue
        geometry = ogr.ForceToMultiPolygon(geometry)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("objektidentitet", str(uuid.uuid4()))
        feature.SetField("versiongiltigfran", now.year, now.month, now.day, now.hour, now.minute, now.second, 0)
        feature.SetField("innehallstyp_varde", "Plangeometri")
        feature.SetField("namn", plan.kommunnamn)
        feature.SetField("under_ersattning", 0)
        feature.SetField("illustrativa_granser", 1)
        feature.SetField("datum_paborjat", d.year, d.month, d.day, 0, 0, 0, 0)
        feature.SetGeometry(geometry)
        layer.CreateFeature(feature)


def _create_meta(ds: ogr.DataSource, values: dict[str, str]) -> None:
    layer = ds.CreateLayer(model.META_TABLE, geom_type=ogr.wkbNone, options=["FID=fid"])
    layer.CreateField(ogr.FieldDefn("key", ogr.OFTString))
    layer.CreateField(ogr.FieldDefn("value", ogr.OFTString))
    for key, value in values.items():
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("key", key)
        feature.SetField("value", value)
        layer.CreateFeature(feature)


def read_only_uri(path: str | Path) -> str:
    """Adress för att öppna en SQLite-fil skrivskyddat (``sqlite3.connect(uri, uri=True)``). En nätverkssökväg
    (//server/resurs/fil) måste skrivas med fyra snedstreck, annars tolkas servernamnet som en ogiltig "authority".
    Tecken som #, ? och mellanslag i sökvägen kodas."""
    posix = quote(Path(path).as_posix(), safe="/:")
    return ("file:////" + posix.lstrip("/") if posix.startswith("//") else f"file:{posix}") + "?mode=ro"


def snapshot(path: str | Path, target: str | Path) -> Path:
    """Kopierar en GeoPackage till ``target`` som en konsekvent ögonblicksbild (SQLites backup), även medan QGIS har
    filen öppen. Originalet öppnas skrivskyddat och rörs inte. Från Rita Detaljplan."""
    source = sqlite3.connect(read_only_uri(path), uri=True)
    try:
        copy = sqlite3.connect(str(target))
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    return Path(target)


def read_meta(path: str | Path) -> dict[str, str]:
    """Pluginets metadata i filen, eller en tom ordbok om filen inte är en översiktsplan skapad av pluginet."""
    try:
        with closing(sqlite3.connect(read_only_uri(path), uri=True)) as con:
            return dict(con.execute(f'SELECT key, value FROM "{model.META_TABLE}"').fetchall())
    except sqlite3.Error:
        return {}


def read_lookup_values(path: str | Path, lookup: model.LookupDef) -> dict[str, dict[str, str]]:
    """Värdena i en uppslagstabell som Lantmäteriets värdeobjekt: värde → ``{varde, vardereferens, grupp,
    gruppreferens}``."""
    with closing(sqlite3.connect(read_only_uri(path), uri=True)) as con:
        rows = con.execute(f'SELECT "{lookup.value_column}", vardereferens, grupp_varde, gruppreferens '
                           f'FROM "{lookup.name}" ORDER BY fid').fetchall()
    return {row[0]: {"varde": row[0], "vardereferens": row[1], "grupp": row[2], "gruppreferens": row[3]}
            for row in rows if row[0]}


def read_lookup(path: str | Path, lookup: model.LookupDef) -> list[str]:
    """Värdena i en uppslagstabell i filen, i den ordning de står där. Planen behåller katalogversionen den skapades
    med, därför läses värdena ur filen och inte ur den medföljande katalogen."""
    with closing(sqlite3.connect(read_only_uri(path), uri=True)) as con:
        return [row[0] for row in con.execute(f'SELECT "{lookup.value_column}" FROM "{lookup.name}" ORDER BY fid')]
