"""Hämta riksintressen: frågorna till Boverkets tjänst, sidindelning, fel, och att objekten läggs in i planen (klippta,
utan dubbletter, med riksintressets id och hämtat datum). Nätverket byts mot en låtsasfunktion."""
import datetime
import json
import sys
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from qgis.core import QgsGeometry  # noqa: E402

from rita_oversiktsplan.core import export_lm, relations, riksintressen  # noqa: E402
from rita_oversiktsplan.gui.riksintressen_dialog import RiksintressenDialog  # noqa: E402
from test_tools import ToolCase  # noqa: E402

NATURE = next(s for s in riksintressen.SOURCES if s.varde == "Naturvård")
TOURISM = next(s for s in riksintressen.SOURCES if s.varde == "Turism och rörligt friluftsliv")
AREA = QgsGeometry.fromWkt("MULTIPOLYGON(((0 0, 100 0, 100 100, 0 100, 0 0)))")
TODAY = datetime.date(2027, 3, 1)


def polygon(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def feature(geometry, **properties):
    return {"type": "Feature", "geometry": geometry, "properties": properties}


class FakeService:
    """Svarar på frågor per lager med förberedda objekt, sida för sida."""

    def __init__(self, layers, page=2):
        self.layers, self.page, self.urls = layers, page, []

    def __call__(self, url):
        self.urls.append(url)
        path, query = url.split("?", 1)
        params = dict(urllib.parse.parse_qsl(query))
        layer = int(path.rsplit("/", 2)[-2])
        features = self.layers.get(layer, [])
        offset = int(params["resultOffset"])
        page = features[offset:offset + self.page]
        return json.dumps({"type": "FeatureCollection", "features": page,
                           "exceededTransferLimit": offset + self.page < len(features)})


class QueryTests(unittest.TestCase):
    def test_the_query_asks_for_geojson_within_the_extent_in_the_plans_crs(self):
        url = riksintressen.query_url(12, (1, 2, 3, 4), 3007, offset=1000)
        path, query = url.split("?", 1)
        params = dict(urllib.parse.parse_qsl(query))
        self.assertTrue(path.endswith("/MapServer/12/query"))
        self.assertEqual((params["geometry"], params["inSR"], params["outSR"]), ("1.000,2.000,3.000,4.000", "3007",
                                                                                 "3007"))
        self.assertEqual((params["f"], params["resultOffset"]), ("geojson", "1000"))

    def test_fetching_follows_the_pages_and_reads_the_authoritys_id_and_name(self):
        service = FakeService({12: [feature(polygon(0, 0, 10, 10), RIKSID=str(i), NAMN=f"Område {i}")
                                    for i in range(5)]})
        records = riksintressen.fetch(service, NATURE, (0, 0, 100, 100), 3006)
        self.assertEqual(len(service.urls), 3)
        self.assertEqual([r.ri_id for r in records], ["0", "1", "2", "3", "4"])
        self.assertEqual(records[0].namn, "Område 0")
        self.assertEqual(records[0].varde, "Naturvård")

    def test_placeholder_names_and_blank_ids_are_ignored(self):
        service = FakeService({169: [feature(polygon(0, 0, 10, 10), ORIGINALID=" ", F_Generellt_namn_="Generellt namn",
                                             NAMN="Vänern")]})
        record = riksintressen.fetch(service, TOURISM, (0, 0, 100, 100), 3006)[0]
        self.assertIsNone(record.ri_id)
        self.assertEqual(record.namn, "Vänern")

    def test_an_error_from_the_service_is_reported(self):
        with self.assertRaisesRegex(riksintressen.FetchError, "Invalid query"):
            riksintressen.fetch(lambda url: json.dumps({"error": {"message": "Invalid query"}}), NATURE,
                                (0, 0, 1, 1), 3006)
        with self.assertRaisesRegex(riksintressen.FetchError, "Kunde inte läsa"):
            riksintressen.fetch(lambda url: "<html>", NATURE, (0, 0, 1, 1), 3006)

    def test_duplicates_from_several_layers_are_removed(self):
        record = riksintressen.Record("Naturvård", polygon(0, 0, 1, 1), "1")
        self.assertEqual(len(riksintressen.unique([record, riksintressen.Record("Naturvård", polygon(0, 0, 1, 1), "1"),
                                                   riksintressen.Record("Naturvård", polygon(0, 0, 2, 2), "1")])), 2)


class ImportTests(ToolCase):
    def layer(self, suffix):
        return self.layers[f"innehall_op_riksintressen_{suffix}"]

    def test_imported_areas_are_clipped_and_carry_the_id_and_the_date(self):
        records = [riksintressen.Record("Naturvård", polygon(50, 50, 150, 150), "1006", "Myren"),
                   riksintressen.Record("Naturvård", polygon(200, 200, 300, 300), "1007", "Utanför")]
        added = riksintressen.import_records(self.group, records, AREA, TODAY)
        self.assertEqual(sum(added.values()), 1)
        f = next(self.layer("polygon").getFeatures())
        self.assertEqual((f["innehallstyp_varde"], f["objektidentitet_ri"], f["namn"]), ("Naturvård", "1006", "Myren"))
        self.assertEqual(f["hamtatdatum"].toPyDate(), TODAY)
        self.assertAlmostEqual(f.geometry().area(), 2500)

    def test_a_second_fetch_adds_nothing_new(self):
        records = [riksintressen.Record("Naturvård", polygon(10, 10, 20, 20), "1006", "Myren"),
                   riksintressen.Record("Turism och rörligt friluftsliv", polygon(0, 0, 100, 40), None, "Vänern"),
                   riksintressen.Record("Naturvård", {"type": "MultiPoint", "coordinates": [[5, 5], [6, 6]]}, "P1")]
        first = riksintressen.import_records(self.group, records, AREA, TODAY)
        self.assertEqual(sum(first.values()), 4)  # multipunkten blir två punkter
        self.assertEqual(riksintressen.import_records(self.group, records, AREA, TODAY), {})

    def test_all_parts_of_a_riksintresse_are_imported(self):
        records = [riksintressen.Record("Naturvård", polygon(10, 10, 20, 20), "1006"),
                   riksintressen.Record("Naturvård", polygon(30, 30, 40, 40), "1006")]
        self.assertEqual(sum(riksintressen.import_records(self.group, records, AREA, TODAY).values()), 2)


class PositionTests(ToolCase):
    def setUp(self):
        super().setUp()
        records = [riksintressen.Record("Naturvård", polygon(10, 10, 20, 20), "1006", "Myren"),
                   riksintressen.Record("Kulturmiljövård", polygon(30, 30, 40, 40), "KR07", "Kålland")]
        riksintressen.import_records(self.group, records, AREA, TODAY)
        self.sources = list(self.layers["innehall_op_riksintressen_polygon"].getFeatures())
        self.positions = self.layers["innehall_op_riksintressenop_polygon"]

    def test_a_position_copies_the_riksintresse_and_concerns_it(self):
        added = riksintressen.create_positions(self.group, self.sources[:1])
        self.assertEqual(sum(added.values()), 1)
        position = next(self.positions.getFeatures())
        source = self.sources[0]
        self.assertEqual((position["innehallstyp_varde"], position["namn"], position["objektidentitet_ri"]),
                         ("Naturvård", "Myren", "1006"))
        self.assertEqual(position.geometry().asWkt(2), source.geometry().asWkt(2))
        self.assertNotEqual(position["objektidentitet"], source["objektidentitet"])
        self.assertEqual(relations.related(self.group, self.positions, position.id()), {source["objektidentitet"]})

    def test_a_riksintresse_gets_only_one_position(self):
        riksintressen.create_positions(self.group, self.sources[:1])
        self.assertEqual(riksintressen.create_positions(self.group, self.sources), {
            "Riksintresse, kommunens ställningstagande (yta)": 1})
        self.assertEqual(self.positions.featureCount(), 2)

    def test_the_export_links_the_position_to_the_riksintresse(self):
        riksintressen.create_positions(self.group, self.sources[:1])
        collection, _ = export_lm.export(self.group)
        content = [f["properties"] for f in collection["features"] if f["properties"]["feature:typ"] == "innehallOP"]
        position = next(c for c in content if c["innehallstyp"]["grupp"].startswith("Riksintresse kommunens"))
        self.assertEqual(position["berorAnnatInnehall"], [str(self.sources[0]["objektidentitet"])])

    def test_selected_riksintressen_are_the_sources(self):
        layer = self.layers["innehall_op_riksintressen_polygon"]
        layer.selectByIds([self.sources[1].id()])
        self.assertEqual([f["namn"] for f in riksintressen.selected_sources(self.group)], ["Kålland"])

    def test_importing_with_positions_copies_each_new_riksintresse(self):
        records = [riksintressen.Record("Naturvård", polygon(50, 50, 60, 60), "1007", "Ny")]
        added = riksintressen.import_records(self.group, records, AREA, TODAY, positions=True)
        self.assertEqual(added, {"Riksintressen enligt 3 och 4 kap. MB (yta)": 1,
                                 "Riksintresse, kommunens ställningstagande (yta)": 1})
        self.assertEqual([f["namn"] for f in self.positions.getFeatures()], ["Ny"])
        self.assertEqual(riksintressen.import_records(self.group, records, AREA, TODAY, positions=True), {})


class DialogTests(ToolCase):
    def test_the_dialog_fetches_the_chosen_riksintressen_within_the_plan(self):
        service = FakeService({12: [feature(polygon(10, 10, 20, 20), RIKSID="1006", NAMN="Myren")]})
        dialog = RiksintressenDialog(self.group, 3006, AREA, None, get=service)
        self.addCleanup(dialog.deleteLater)
        for source, box in dialog.boxes.items():
            box.setChecked(source is NATURE)
        self.assertTrue(dialog.use_plan.isChecked())
        self.assertEqual(sum(dialog.fetch().values()), 1)
        self.assertIn("1 lades in", dialog.message.text())
        self.assertTrue(all("/12/query" in url for url in service.urls))

    def test_without_a_plan_area_the_map_extent_is_used_and_nothing_is_clipped(self):
        dialog = RiksintressenDialog(self.group, 3006, None, None, get=FakeService({}))
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.use_plan.isEnabled())
        self.assertTrue(dialog.use_map.isChecked())
        self.assertIsNone(dialog.fetch())
        self.assertIn("inget område", dialog.message.text())


if __name__ == "__main__":
    unittest.main()
