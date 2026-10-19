"""GeoPackage-filen för en ny översiktsplan (kräver QGIS Python för GDAL) och laddningen i ett QGIS-projekt."""
import datetime
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsGeometry, QgsProject, QgsRenderContext,  # noqa: E402
                       QgsSldExportContext, QgsWkbTypes)

from rita_oversiktsplan.core import geopackage, model, project, styles, symbology  # noqa: E402

PLAN = geopackage.NewPlan(kommunkod="0484", kommunnamn="Eskilstuna", titel="Översiktsplan 2040",
                          datum_paborjat=datetime.date(2027, 1, 15))


class PlanFileCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.path = geopackage.create_geopackage(Path(self.tmp.name) / "op.gpkg", PLAN)

    def query(self, sql):
        with closing(sqlite3.connect(self.path)) as con:
            return con.execute(sql).fetchall()


class GeoPackageTests(PlanFileCase):
    def test_it_has_every_table_in_the_model_and_every_lookup(self):
        tables = {row[0] for row in self.query("SELECT table_name FROM gpkg_contents")}
        for name in [layer.name for layer in model.LAYERS] + [lookup.name for lookup in model.LOOKUPS]:
            self.assertIn(name, tables)

    def test_all_geometry_layers_are_in_sweref_99_tm(self):
        rows = self.query("SELECT table_name, column_name, srs_id FROM gpkg_geometry_columns")
        self.assertEqual(len(rows), len(model.CONTENT_LAYERS) + len(model.DRAFT_LAYERS))
        self.assertEqual({(column, srs) for _, column, srs in rows}, {("geom", 3006)})

    def test_the_plan_row_holds_the_values_from_the_dialog_and_a_uuid(self):
        (row,) = self.query("SELECT objektidentitet, kommunkod, kommunnamn, planens_titel, datum_paborjat, "
                            "digitalt_ursprung, versiongiltigfran FROM oversiktsplan")
        identity, kod, namn, titel, paborjat, digital, version = row
        self.assertRegex(identity, r"^[0-9a-f-]{36}$")
        self.assertEqual((kod, namn, titel, paborjat, digital), ("0484", "Eskilstuna", "Översiktsplan 2040",
                                                                 "2027-01-15", 1))
        self.assertTrue(version)

    def test_lookups_are_filled_from_the_current_catalog_with_ids(self):
        rows = self.query("SELECT innehallstyp_varde, vardereferens, grupp_varde, version_opkatalogen "
                          "FROM innehall_op_markochvattenanvandning_lookup")
        self.assertEqual(len(rows), 21)
        self.assertIn(("Bostadsbebyggelse", "2b17bfa0-235d-49ac-8c7d-24afb9f22b8b", "Mark- och vattenanvändning",
                       "2.2"), rows)
        planhandelser = [r[0] for r in self.query("SELECT planhandelse_varde FROM planhandelse_lookup")]
        self.assertIn("Angivet innehåll fastställt som inaktuellt", planhandelser)  # ny i katalogen 2.1

    def test_a_new_plan_has_unassigned_layers_and_default_values_from_the_start(self):
        tables = {row[0] for row in self.query("SELECT table_name FROM gpkg_contents")}
        self.assertTrue({"rita_otilldelad_yta", "rita_otilldelad_linje", "rita_otilldelad_punkt"} <= tables)
        self.assertEqual(geopackage.read_defaults(self.path), {"vertikal_avgransning": "", "under_ersattning": "0",
                                                               "datum_paborjat": "", "presentationsskala": ""})

    def test_default_values_are_written_and_read_back(self):
        geopackage.write_defaults(self.path, {"vertikal_avgransning": "uppåt", "presentationsskala": "25000"})
        defaults = geopackage.read_defaults(self.path)
        self.assertEqual((defaults["vertikal_avgransning"], defaults["presentationsskala"]), ("uppåt", "25000"))

    def test_the_meta_table_records_versions(self):
        meta = geopackage.read_meta(self.path)
        self.assertEqual(meta["schema_version"], str(model.SCHEMA_VERSION))
        self.assertEqual(meta["databasmodell"], "0.3")
        self.assertEqual(meta["opkatalog_version"], "2.2")

    def test_an_existing_file_is_never_overwritten(self):
        with self.assertRaises(FileExistsError):
            geopackage.create_geopackage(self.path, PLAN)

    def test_a_file_that_is_not_a_plan_has_no_meta(self):
        other = Path(self.tmp.name) / "annan.gpkg"
        with closing(sqlite3.connect(other)) as con:
            con.execute("CREATE TABLE t (a)")
        self.assertEqual(geopackage.read_meta(other), {})


class CoordinateSystemTests(unittest.TestCase):
    def test_a_plan_can_use_a_local_sweref_zone_all_the_way_to_the_export(self):
        import dataclasses

        from qgis.core import QgsGeometry, QgsProject

        from rita_oversiktsplan.core import export_lm, storage
        from rita_oversiktsplan.core.project import load_plan

        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        path = geopackage.create_geopackage(Path(tmp.name) / "zon.gpkg", dataclasses.replace(PLAN, epsg=3010))
        self.assertEqual(geopackage.read_meta(path)["epsg"], "3010")
        self.assertEqual(storage.GeoPackageStorage(path).epsg, 3010)
        project = QgsProject.instance()
        self.addCleanup(project.clear)
        layers = load_plan(path, project)
        self.assertEqual(layers["rita_otilldelad_yta"].crs().authid(), "EPSG:3010")
        self.assertEqual(project.crs().authid(), "EPSG:3010")
        self.assertEqual(export_lm.geometry(QgsGeometry.fromWkt("POINT(1 2)"), 3010)["koordinatsystemPlan"],
                         "EPSG:3010")

    def test_only_sweref_99_is_allowed(self):
        import dataclasses

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            with self.assertRaises(ValueError):
                geopackage.create_geopackage(Path(folder) / "x.gpkg", dataclasses.replace(PLAN, epsg=4326))


class LoadPlanTests(PlanFileCase):
    def setUp(self):
        super().setUp()
        self.project = QgsProject()
        self.addCleanup(self.project.clear)
        self.layers = project.load_plan(self.path, self.project)

    def test_the_plan_gets_its_own_group_named_after_the_title(self):
        (group,) = project.plan_groups(self.project)
        self.assertEqual(group.name(), "Översiktsplan – Översiktsplan 2040")
        self.assertEqual(self.project.crs().authid(), "EPSG:3006")

    def test_content_types_are_subgroups_with_area_line_and_point(self):
        (group,) = project.plan_groups(self.project)
        mva = group.findGroup("Mark- och vattenanvändning")
        names = [child.name() for child in mva.children()]
        self.assertEqual(names, ["Mark- och vattenanvändning (punkt)", "Mark- och vattenanvändning (linje)",
                                 "Mark- och vattenanvändning (yta)"])  # det översta ritas överst

    def test_points_are_drawn_over_lines_and_lines_over_areas(self):
        order = [layer.customProperty(project.TABLE_PROPERTY) for layer in self.project.layerTreeRoot().layerOrder()]
        for prefix in ("innehall_op_utvecklingsinriktning", "innehall_op_klimatrelateradrisk",
                       "innehall_op_markochvattenanvandning"):
            self.assertLess(order.index(f"{prefix}_point"), order.index(f"{prefix}_line"))
            self.assertLess(order.index(f"{prefix}_line"), order.index(f"{prefix}_polygon"))
        self.assertLess(order.index("rita_otilldelad_punkt"), order.index("rita_otilldelad_yta"))

    def test_land_use_is_the_bottom_of_the_plan_under_the_overlays(self):
        order = [layer.customProperty(project.TABLE_PROPERTY) for layer in self.project.layerTreeRoot().layerOrder()]
        land_use = order.index("innehall_op_markochvattenanvandning_polygon")
        overlays = [t for t in order if t and t.startswith("innehall_op_") and "markochvatten" not in t]
        self.assertTrue(all(order.index(t) < land_use for t in overlays))
        self.assertEqual(self.layers["innehall_op_markochvattenanvandning_point"].geometryType(),
                         QgsWkbTypes.GeometryType.PointGeometry)

    def test_every_table_is_loaded(self):
        self.assertEqual(set(self.layers), {layer.name for layer in model.LAYERS})

    def test_the_content_type_is_a_list_of_the_catalog_values_in_the_file(self):
        layer = self.layers["innehall_op_markochvattenanvandning_polygon"]
        setup = layer.editorWidgetSetup(layer.fields().indexOf("innehallstyp_varde"))
        self.assertEqual(setup.type(), "ValueMap")
        values = [next(iter(entry)) for entry in setup.config()["map"]]
        self.assertIn("Bostadsbebyggelse", values)
        self.assertEqual(len(values), 21)

    def test_new_content_gets_a_uuid_and_illustrative_boundaries(self):
        layer = self.layers["innehall_op_lis_polygon"]
        fields = layer.fields()
        uuid = layer.defaultValueDefinition(fields.indexOf("objektidentitet")).expression()
        self.assertIn("uuid", uuid)
        self.assertEqual(layer.defaultValueDefinition(fields.indexOf("illustrativa_granser")).expression(), "true")
        self.assertEqual(layer.editorWidgetSetup(fields.indexOf("objektidentitet")).type(), "Hidden")

    def test_new_content_takes_the_plans_current_plan_event(self):
        layer = self.layers["innehall_op_lis_polygon"]
        expression = layer.defaultValueDefinition(layer.fields().indexOf("planhandelse_varde")).expression()
        self.assertIn(self.layers["oversiktsplan"].id(), expression)

    def test_land_use_is_drawn_with_one_symbol_per_catalog_value_in_detailed_plan_colours(self):
        renderer = self.layers["innehall_op_markochvattenanvandning_polygon"].renderer()
        self.assertIsInstance(renderer, QgsCategorizedSymbolRenderer)
        self.assertEqual(renderer.classAttribute(), "innehallstyp_varde")
        categories = {c.value(): c for c in renderer.categories()}
        self.assertEqual(len(categories), 21 + 1)  # värdena + "ej vald"
        bostad = categories["Bostadsbebyggelse"].symbol().symbolLayer(0).color()
        self.assertEqual((bostad.red(), bostad.green(), bostad.blue()), (255, 255, 206))  # Gul, som B i detaljplan
        self.assertEqual(renderer.categories()[-1].label(), "Innehållstyp ej vald")

    def test_content_without_a_type_is_drawn_as_not_chosen(self):
        layer = self.layers["innehall_op_lis_polygon"]
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"))
        context = QgsRenderContext()
        renderer = layer.renderer().clone()
        renderer.startRender(context, layer.fields())
        try:
            symbol = renderer.symbolForFeature(feature, context)
        finally:
            renderer.stopRender(context)
        self.assertIsNotNone(symbol)
        color = symbol.symbolLayer(1).color()  # kanten
        self.assertEqual((color.red(), color.green(), color.blue()), styles.UNASSIGNED_COLOR)

    def test_lines_and_points_are_classified_the_same_way(self):
        for table in ("innehall_op_markochvattenanvandning_line", "innehall_op_klimatrelateradrisk_point"):
            renderer = self.layers[table].renderer()
            self.assertIsInstance(renderer, QgsCategorizedSymbolRenderer, table)
        values = [c.value() for c in self.layers["innehall_op_klimatrelateradrisk_point"].renderer().categories()]
        self.assertIn("Risk för översvämning", values)

    def test_development_direction_is_classified_on_the_complementary_value(self):
        renderer = self.layers["innehall_op_utvecklingsinriktning_polygon"].renderer()
        filters = [r.filterExpression() for r in renderer.rootRule().children()]
        self.assertIn("\"kompletterandeInnehallstyp\" = 'Grön- och blåstruktur'", filters)

    def test_overlays_have_a_faint_fill_so_land_use_shows_through(self):
        renderer = self.layers["innehall_op_riksintressenop_polygon"].renderer()
        category = next(c for c in renderer.categories() if c.value() == "Naturvård")
        self.assertEqual(category.symbol().symbolLayer(0).color().alpha(), styles.OVERLAY_ALPHA)

    def test_every_symbol_is_built_from_simple_symbol_layers_only(self):
        for table, layer in self.layers.items():
            if not isinstance(layer.renderer(), QgsCategorizedSymbolRenderer):
                continue
            for category in layer.renderer().categories():
                symbol = category.symbol()
                self.assertLessEqual(symbol.symbolLayerCount(), 2, f"{table}: {category.value()}")
                for i in range(symbol.symbolLayerCount()):
                    self.assertIn(symbol.symbolLayer(i).layerType(), symbology.SIMPLE_LAYER_TYPES,
                                  f"{table}: {category.value()}")

    def test_the_style_exports_to_sld_for_geoserver_with_only_standard_parts(self):
        for table in ("innehall_op_markochvattenanvandning_polygon", "innehall_op_riksintressen_polygon",
                      "innehall_op_klimatrelateradrisk_line", "innehall_op_riksintressenop_point",
                      "innehall_op_lansstyrelsensinvandning_point"):
            context = QgsSldExportContext()
            sld = self.layers[table].exportSldStyleV3(context).toString()
            self.assertIn("<se:Rule>", sld, table)
            for unwanted in ("GraphicFill", "GraphicStroke", "ExternalGraphic", "ttf://"):
                self.assertNotIn(unwanted, sld, table)  # mönster, bilder och typsnitt, som många webbkartor saknar
            for shape in re.findall(r"<se:WellKnownName>(.*?)</se:WellKnownName>", sld):
                self.assertIn(shape, ("circle", "square", "triangle", "star", "cross"), table)
            self.assertEqual(list(context.errors()), [], table)
        sld = self.layers["innehall_op_riksintressenop_polygon"].exportSldStyleV3(QgsSldExportContext()).toString()
        self.assertIn("fill-opacity", sld)
        self.assertNotIn("<ogc:Function", sld)  # bara vanliga jämförelser i filtren
        self.assertIn("<se:ElseFilter", sld)  # klassen utan värde
        sld = self.layers["innehall_op_klimatrelateradrisk_polygon"].exportSldStyleV3(QgsSldExportContext()).toString()
        self.assertIn("stroke-dasharray", sld)
        points = self.layers["innehall_op_miljokvalitetsnormer_point"].exportSldStyleV3(QgsSldExportContext())
        self.assertIn("<se:Rotation>", points.toString())  # romben är en vriden kvadrat

    def test_the_same_plan_cannot_be_opened_twice(self):
        with self.assertRaisesRegex(project.PlanError, "redan öppen"):
            project.load_plan(self.path, self.project)

    def test_a_geopackage_from_elsewhere_is_refused_with_a_clear_message(self):
        other = Path(self.tmp.name) / "annan.gpkg"
        with closing(sqlite3.connect(other)) as con:
            con.execute("CREATE TABLE t (a)")
        with self.assertRaisesRegex(project.PlanError, "inte en översiktsplan"):
            project.load_plan(other, QgsProject())


if __name__ == "__main__":
    unittest.main()
