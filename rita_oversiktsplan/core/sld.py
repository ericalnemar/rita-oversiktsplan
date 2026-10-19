"""Stilfiler (SLD) för GeoServer. Ren Python.

QGIS skriver en punkt i en linjes ände (utvecklingsinriktningens pilspetsar) som en ``LineSymbolizer`` med
``GraphicStroke`` och inställningen ``<VendorOption name="placement">lastPoint</VendorOption>``. Den inställningen är
QGIS egen. GeoServer ritar i stället en punkt i linjens ände med geometrifunktionerna ``endPoint``/``startPoint`` och
vrider den med ``endAngle``/``startAngle`` (GeoServers dokumentation: *Geometry transformations in SLD*). Den här
modulen gör om QGIS form till GeoServers. Allt annat i filen lämnas orört.

Inte provat i en riktig GeoServer. Vridningen bygger på att GeoServers vinkel räknas så att en symbol som pekar åt
höger följer linjen; QGIS triangel pekar uppåt och vrids därför 90° (eller 270° för pilen i linjens början, som
pekar bakåt), samma vridning som QGIS själv använder."""
from __future__ import annotations

import xml.etree.ElementTree as ET

SE = "http://www.opengis.net/se"
OGC = "http://www.opengis.net/ogc"
NAMESPACES = {"sld": "http://www.opengis.net/sld", "se": SE, "ogc": OGC,
              "xlink": "http://www.w3.org/1999/xlink", "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
ENDS = {"lastPoint": ("endPoint", "endAngle"), "firstPoint": ("startPoint", "startAngle")}

for prefix, uri in NAMESPACES.items():
    ET.register_namespace("" if prefix == "sld" else prefix, uri)


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def _function(name: str, geometry: str) -> ET.Element:
    function = ET.Element(_q(OGC, "Function"), {"name": name})
    ET.SubElement(function, _q(OGC, "PropertyName")).text = geometry
    return function


def _rotation(graphic: ET.Element, angle_function: str, geometry: str) -> None:
    """Pilens vridning = linjens vinkel i änden + den vridning QGIS gav symbolen (90° framåt, 270° bakåt)."""
    old = graphic.find(_q(SE, "Rotation"))
    offset = "0"
    if old is not None:
        literal = old.find(_q(OGC, "Literal"))
        offset = literal.text if literal is not None and literal.text else "0"
        graphic.remove(old)
    rotation = ET.Element(_q(SE, "Rotation"))
    add = ET.SubElement(rotation, _q(OGC, "Add"))
    add.append(_function(angle_function, geometry))
    ET.SubElement(add, _q(OGC, "Literal")).text = offset
    # Rotation ska stå sist i Graphic enligt schemat (efter Mark, Opacity, Size)
    graphic.append(rotation)


def _converted(symbolizer: ET.Element, placement: str, geometry: str) -> ET.Element | None:
    graphic = symbolizer.find(f"{_q(SE, 'Stroke')}/{_q(SE, 'GraphicStroke')}/{_q(SE, 'Graphic')}")
    if graphic is None:
        return None
    point_function, angle_function = ENDS[placement]
    point = ET.Element(_q(SE, "PointSymbolizer"))
    geometry_element = ET.SubElement(point, _q(SE, "Geometry"))
    geometry_element.append(_function(point_function, geometry))
    _rotation(graphic, angle_function, geometry)
    point.append(graphic)
    return point


def for_geoserver(sld: str, geometry: str = "geom") -> str:
    """Gör om pilspetsar i linjeändar till GeoServers form. ``geometry`` är geometrikolumnens namn i tjänsten
    (``geom`` i pluginets GeoPackage och PostGIS-schema)."""
    root = ET.fromstring(sld)
    for rule in root.iter(_q(SE, "Rule")):
        for index, symbolizer in enumerate(list(rule)):
            if symbolizer.tag != _q(SE, "LineSymbolizer"):
                continue
            option = symbolizer.find(_q(SE, "VendorOption"))
            if option is None or option.get("name") != "placement" or option.text not in ENDS:
                continue
            point = _converted(symbolizer, option.text, geometry)
            if point is not None:
                rule.remove(symbolizer)
                rule.insert(index, point)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
