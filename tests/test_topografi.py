"""Markanvändning från Topografi 10: en låtsad nedladdning (zip med en GeoPackage per tema, samma skikt och fält som
Lantmäteriets) omklassas till mark- och vattenanvändning som yta, linje och punkt, och dialogen som gör det."""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from osgeo import ogr, osr  # noqa: E402
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsSettings  # noqa: E402

from rita_oversiktsplan.core import styles, topografi  # noqa: E402
from rita_oversiktsplan.core.topografi import Key  # noqa: E402
from rita_oversiktsplan.gui import topografi_dialog  # noqa: E402
from rita_oversiktsplan.gui.topografi_dialog import TopografiDialog  # noqa: E402
from test_tools import ToolCase  # noqa: E402

CRS = QgsCoordinateReferenceSystem("EPSG:3006")
PLAN = QgsGeometry.fromWkt("POLYGON((0 0, 3000 0, 3000 1000, 0 1000, 0 0))")


def square(x0, y0, x1, y1):
    return f"POLYGON(({x0} {y0}, {x1} {y0}, {x1} {y1}, {x0} {y1}, {x0} {y0}))"


THEMES = {
    "mark": {"mark": (ogr.wkbMultiPolygon, [
        ("Barr- och blandskog", "", square(0, 0, 500, 1000)),
        ("Lövskog", "", square(500, 0, 1000, 1000)),
        ("Öppen mark", "", square(400, 400, 420, 420)),  # liten glänta: tas med ändå
        ("Åker", "", square(1000, 0, 2000, 1000)),
        ("Sjö", "", square(2000, 0, 3000, 1000)),
        ("Låg bebyggelse", "", square(5000, 5000, 5300, 5300))])},  # utanför planen
    "anlaggningsomrade": {"anlaggningsomrade": (ogr.wkbMultiPolygon, [
        ("Rekreation", "Golfbana", square(1200, 200, 1600, 600)),  # ovanpå åkern
        ("Rekreation", "Parkområde", square(100, 100, 200, 200))])},  # ovanpå skogen
    "kommunikation": {"vaglinje": (ogr.wkbMultiLineString, [
        ("Landsväg", "", "LINESTRING(0 500, 1500 500)"),
        ("Landsväg", "", "LINESTRING(1500 500, 2900 500)"),  # fortsättning: blir en linje
        ("Lokalgata liten", "", "LINESTRING(0 100, 900 100)")])},  # tas inte med
    "hydro": {"hydrolinje": (ogr.wkbMultiLineString, [("Vattendrag", "", "LINESTRING(50 0, 50 1000)")])},
    "byggnadsverk": {"byggnadspunkt": (ogr.wkbPoint, [("Vindkraftverk", "", "POINT(1100 900)"),
                                                     ("Kyrka", "", "POINT(1300 900)")])},
}


def make_topografi(folder: Path) -> Path:
    """En zip-fil som Lantmäteriets nedladdning: en GeoPackage per tema."""
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3006)
    archive = folder / "topografi10_kn1494.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for theme, layers in THEMES.items():
            path = folder / f"{theme}.gpkg"
            ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
            for name, (geometry_type, rows) in layers.items():
                layer = ds.CreateLayer(name, srs, geometry_type)
                layer.CreateField(ogr.FieldDefn("objekttyp", ogr.OFTString))
                if theme == "anlaggningsomrade":
                    layer.CreateField(ogr.FieldDefn("andamal", ogr.OFTString))
                for objekttyp, andamal, wkt in rows:
                    feature = ogr.Feature(layer.GetLayerDefn())
                    feature.SetField("objekttyp", objekttyp)
                    if andamal:
                        feature.SetField("andamal", andamal)
                    geometry = ogr.CreateGeometryFromWkt(wkt)
                    if geometry_type == ogr.wkbMultiPolygon:
                        geometry = ogr.ForceToMultiPolygon(geometry)
                    elif geometry_type == ogr.wkbMultiLineString:
                        geometry = ogr.ForceToMultiLineString(geometry)
                    feature.SetGeometry(geometry)
                    layer.CreateFeature(feature)
            ds = None
            z.write(path, f"{theme}.gpkg")
    return archive


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.zip = make_topografi(Path(self.tmp.name))

    def test_every_theme_in_the_zip_file_is_read(self):
        keys = topografi.read_keys(self.zip)
        self.assertIn(Key("anlaggningsomrade", "Rekreation", "Golfbana", "polygon"), keys)
        self.assertIn(Key("vaglinje", "Landsväg", "", "line"), keys)
        self.assertIn(Key("byggnadspunkt", "Vindkraftverk", "", "point"), keys)
        self.assertEqual(keys[0].kind, "polygon")  # ytor först, sedan linjer och punkter
        self.assertEqual(keys[-1].kind, "point")

    def test_the_proposal_uses_the_purpose_before_the_type(self):
        self.assertEqual(topografi.default_value(Key("a", "Rekreation", "Parkområde")), "Grönområde")
        self.assertEqual(topografi.default_value(Key("a", "Rekreation", "Golfbana")), "Friluftsliv och rekreation")
        self.assertEqual(topografi.default_value(Key("a", "Industriområde", "Rengärde")), "Renskötsel")
        self.assertIsNone(topografi.default_value(Key("v", "Lokalgata liten", "", "line")))
        self.assertIsNone(topografi.default_value(Key("x", "Okänd typ")))

    def test_buildings_and_points_are_never_proposed(self):
        self.assertIsNone(topografi.default_value(Key("byggnad", "Samhällsfunktion")))  # heter som anläggningen
        self.assertIsNone(topografi.default_value(Key("byggnadspunkt", "Vindkraftverk", "", "point")))
        self.assertIsNone(topografi.default_value(Key("ralstrafikstation", "Järnvägsstation", "", "point")))
        self.assertEqual(topografi.default_value(Key("anlaggningsomrade", "Samhällsfunktion")), "Service")

    def test_forest_fields_and_open_land_are_proposed_as_landsbygd(self):
        for objekttyp in ("Öppen mark", "Åker", "Barr- och blandskog", "Lövskog"):
            self.assertEqual(topografi.default_value(Key("mark", objekttyp)), "Landsbygd", objekttyp)

    def test_everything_is_classified_merged_and_clipped_whatever_its_size(self):
        mapping = topografi.mapping_for(topografi.read_keys(self.zip))
        built = topografi.build(self.zip, mapping, PLAN, CRS)
        self.assertEqual(set(built), {("polygon", "Landsbygd"), ("polygon", "Vatten"), ("polygon", "Grönområde"),
                                      ("polygon", "Friluftsliv och rekreation"), ("line", "Vägtrafik"),
                                      ("line", "Vatten")})  # inga punkter föreslås
        golf, _ = built[("polygon", "Friluftsliv och rekreation")]
        self.assertAlmostEqual(golf[0].area(), 160_000)
        park, _ = built[("polygon", "Grönområde")]
        self.assertAlmostEqual(park[0].area(), 10_000)
        countryside, labels = built[("polygon", "Landsbygd")]
        self.assertEqual(len(countryside), 1)  # skog, glänta och åker blir en yta
        self.assertAlmostEqual(countryside[0].area(), 2_000_000 - 160_000 - 10_000)  # golf och park går före
        self.assertEqual(labels, ["Barr- och blandskog", "Lövskog", "Åker", "Öppen mark"])
        road, labels = built[("line", "Vägtrafik")]
        self.assertEqual(len(road), 1)  # två väglänkar som möts blir en linje
        self.assertAlmostEqual(road[0].length(), 2900)
        self.assertEqual(labels, ["Landsväg"])

    def test_a_marktacke_file_works_the_same_way(self):
        mark = Path(self.tmp.name) / "mark.gpkg"
        built = topografi.build(mark, topografi.mapping_for(topografi.read_keys(mark)), PLAN, CRS)
        self.assertIn(("polygon", "Landsbygd"), built)


class PlanTests(ToolCase):
    def setUp(self):
        super().setUp()
        self.zip = make_topografi(Path(self.tmp.name))

    def test_the_result_lands_in_the_plan_and_a_new_run_replaces_it(self):
        drawn = self.assigned(values={"innehallstyp_varde": "Bostadsbebyggelse", "namn": "Ritad"})
        drawn.layer.commitChanges(False)
        built = topografi.build(self.zip, topografi.mapping_for(topografi.read_keys(self.zip)), PLAN, CRS)
        added, removed = topografi.add_to_plan(self.group, built)
        self.assertEqual(added["Vägtrafik (linje)"], 1)
        self.assertNotIn("Energiproduktion (punkt)", added)
        lines = self.layers[topografi.LAYERS["line"]]
        road = next(f for f in lines.getFeatures() if f["innehallstyp_varde"] == "Vägtrafik")
        self.assertEqual(road["precisering"], "Från Lantmäteriet (Landsväg)")
        again, removed = topografi.add_to_plan(self.group, built)
        self.assertEqual(removed, sum(added.values()))
        polygons = self.layers[topografi.LAYERS["polygon"]]
        self.assertEqual(len([f for f in polygons.getFeatures() if f["namn"] == "Ritad"]), 1)


class HeightTests(ToolCase):
    """Lantmäteriets data har höjdvärden (Z). Planens lager är plana: utan omvandling gick inget att spara
    ("geometritypen stämmer inte överens med det aktuella lagret", användarens prov 2026-10-20)."""

    def test_areas_and_lines_with_heights_can_be_saved(self):
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(3006)
        path = Path(self.tmp.name) / "marktacke_z.gpkg"
        ds = ogr.GetDriverByName("GPKG").CreateDataSource(str(path))
        for name, kind, objekttyp, wkt in (
                ("mark", ogr.wkbMultiPolygon25D, "Åker", "MULTIPOLYGON Z (((0 0 10, 900 0 12, 900 900 11, 0 900 10, "
                                                          "0 0 10)))"),
                ("vaglinje", ogr.wkbMultiLineString25D, "Landsväg", "MULTILINESTRING Z ((0 450 10, 900 450 12))")):
            layer = ds.CreateLayer(name, srs, kind)
            layer.CreateField(ogr.FieldDefn("objekttyp", ogr.OFTString))
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetField("objekttyp", objekttyp)
            feature.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
            layer.CreateFeature(feature)
        ds = None
        built = topografi.build(path, topografi.mapping_for(topografi.read_keys(path)), PLAN, CRS)
        topografi.add_to_plan(self.group, built)
        for kind in ("polygon", "line"):
            layer = self.layers[topografi.LAYERS[kind]]
            self.assertTrue(layer.commitChanges(False), (kind, layer.commitErrors()))
            self.assertEqual(layer.featureCount(), 1, kind)


class DialogTests(ToolCase):
    def setUp(self):
        super().setUp()
        self.zip = make_topografi(Path(self.tmp.name))
        settings = QgsSettings()
        old = settings.value(topografi_dialog.SETTINGS_KEY)
        settings.remove(topografi_dialog.SETTINGS_KEY)
        self.addCleanup(lambda: settings.setValue(topografi_dialog.SETTINGS_KEY, old) if old is not None
                        else settings.remove(topografi_dialog.SETTINGS_KEY))

    def dialog(self, plan_area=PLAN):
        values = list(styles.MARK_OCH_VATTEN)
        dialog = TopografiDialog(self.group, values, CRS, plan_area)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_the_file_fills_the_table_and_a_changed_choice_is_remembered(self):
        dialog = self.dialog()
        dialog.file.setFilePath(str(self.zip))
        self.assertTrue(dialog.run_button.isEnabled())
        self.assertEqual(dialog.value_for("Rekreation – Parkområde"), "Grönområde")
        dialog.set_value("Lokalgata liten", "Vägtrafik")
        added, _ = dialog.run()
        self.assertEqual(added["Vägtrafik (linje)"], 2)  # landsvägen och lokalgatan
        again = self.dialog()
        again.file.setFilePath(str(self.zip))
        self.assertEqual(again.value_for("Lokalgata liten"), "Vägtrafik")
        again.reset()
        self.assertIsNone(again.value_for("Lokalgata liten"))

    def test_there_is_no_minimum_area(self):
        dialog = self.dialog()
        self.assertFalse(hasattr(dialog, "min_area"))


class ColourTests(unittest.TestCase):
    def test_existing_land_use_takes_the_colours_of_topografi_10(self):
        self.assertEqual(styles.MARK_OCH_VATTEN["Skogsbruk"].color, (212, 238, 183))  # Barr- och blandskog
        self.assertEqual(styles.MARK_OCH_VATTEN["Bostadsbebyggelse"].color, (242, 207, 155))  # Låg bebyggelse
        self.assertEqual(styles.MARK_OCH_VATTEN["Vatten"].color, (191, 230, 255))

    def test_roads_are_drawn_in_a_lighter_grey(self):
        self.assertEqual(styles.MARK_OCH_VATTEN["Vägtrafik"].line, styles.LINE_COLORS["Vägtrafik"])
        self.assertGreater(styles.LINE_COLORS["Vägtrafik"][0], styles.darker(styles.MARK_OCH_VATTEN["Vägtrafik"].color,
                                                                              0.65)[0])

    def test_a_grey_stays_grey_in_the_stages(self):
        first, _, last = (styles.stage_color((240, 240, 240), i, 3) for i in range(3))
        self.assertEqual(len(set(first)), 1)  # grått, inte rött
        self.assertLess(first[0], last[0])  # första etappen mörkast


if __name__ == "__main__":
    unittest.main()
