"""Kartografin: utvecklingsinriktningen som kommunschema med pilspetsar, namnetiketter, skalgränser, markanvändningens
täckning och stilfilerna för GeoServer."""
import datetime
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qgis_app import get_app  # noqa: E402

get_app()

from qgis.core import (Qgis, QgsExpression, QgsExpressionContext, QgsFeature, QgsProject,  # noqa: E402
                       QgsRuleBasedRenderer, QgsSldExportContext)

from rita_oversiktsplan import classFactory  # noqa: E402
from rita_oversiktsplan.core import geopackage, project, sld, styles, symbology  # noqa: E402
from test_plugin import FakeIface  # noqa: E402

PLAN = geopackage.NewPlan("0484", "Eskilstuna", "ÖP 2040", datetime.date(2027, 1, 1))
UI = "innehall_op_utvecklingsinriktning_"
MVA = "innehall_op_markochvattenanvandning_polygon"
OGC = "{http://www.opengis.net/ogc}"
SE = "{http://www.opengis.net/se}"


class PlanCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.path = geopackage.create_geopackage(Path(self.tmp.name) / "op.gpkg", PLAN)
        self.project = QgsProject()
        self.addCleanup(self.project.clear)
        self.layers = project.load_plan(self.path, self.project)

    def theme(self, table, value):
        root = self.layers[table].renderer().rootRule()
        return next(r for r in root.children() if r.label() == value)

    def overview(self, table, value):
        """Symbolerna för kommunkartan, en per nivå (den första underregeln under varje nivå)."""
        return [level.children()[0].symbol() for level in self.theme(table, value).children()]


class DevelopmentTests(PlanCase):
    def test_development_is_a_rule_per_theme_with_a_size_per_level(self):
        renderer = self.layers[UI + "line"].renderer()
        self.assertIsInstance(renderer, QgsRuleBasedRenderer)
        labels = [r.label() for r in renderer.rootRule().children()]
        self.assertIn("Bebyggelsestruktur", labels)
        self.assertIn(symbology.WITHOUT_COMPLEMENT_LABEL, labels)
        widths = [symbol.symbolLayer(0).width() for symbol in self.overview(UI + "line", "Kommunikation")]
        self.assertEqual(widths, sorted(widths, reverse=True))  # regional bredast, lokal smalast
        self.assertEqual(len(widths), len(styles.DEVELOPMENT_LEVELS))

    def test_a_theme_has_one_colour_for_areas_lines_and_nodes(self):
        expected = styles.style_for("utvecklingsinriktning", "Bebyggelsestruktur").color
        for suffix in ("polygon", "line", "point"):
            symbol = self.overview(UI + suffix, "Bebyggelsestruktur")[0]
            colors = [symbol.symbolLayer(i).color() for i in range(symbol.symbolLayerCount())]
            self.assertTrue(any((c.red(), c.green(), c.blue()) == expected for c in colors), suffix)

    def arrowheads(self, theme, choice):
        """Pilspetsarna (slut/början) som ritas för en regional linje med temat och valet i rita_pilar."""
        layer = self.layers[UI + "line"]
        feature = QgsFeature(layer.fields())
        feature["kompletterandeInnehallstyp"] = theme
        feature["sambandsniva_varde"] = "Regional"
        feature["rita_pilar"] = choice
        context = QgsExpressionContext()
        context.setFeature(feature)
        overview = self.theme(UI + "line", theme).children()[0].children()[0]
        drawn = set()
        for rule in overview.children():
            placement = rule.symbol().symbolLayer(0).placements()
            if QgsExpression(rule.filterExpression()).evaluate(context):
                drawn.add("slut" if placement == Qgis.MarkerLinePlacement.LastVertex else "början")
        return drawn

    def test_without_a_choice_the_theme_decides_the_arrowheads(self):
        self.assertEqual(self.arrowheads("Bebyggelsestruktur", None), {"slut"})
        self.assertEqual(self.arrowheads("Kommunikation", None), {"slut"})
        self.assertEqual(self.arrowheads("Grön- och blåstruktur", None), {"slut", "början"})

    def test_the_choice_in_the_dialog_decides_the_arrowheads(self):
        self.assertEqual(self.arrowheads("Kommunikation", "båda"), {"slut", "början"})
        self.assertEqual(self.arrowheads("Grön- och blåstruktur", "slut"), {"slut"})
        self.assertEqual(self.arrowheads("Bebyggelsestruktur", "start"), {"början"})
        self.assertEqual(self.arrowheads("Grön- och blåstruktur", "ingen"), set())

    def test_the_band_itself_has_no_arrowhead(self):
        band = self.overview(UI + "line", "Kommunikation")[0]
        self.assertEqual([band.symbolLayer(i).layerType() for i in range(band.symbolLayerCount())], ["SimpleLine"])

    def test_nodes_are_a_ring_around_a_dot_that_shrinks_with_the_level(self):
        symbols = self.overview(UI + "point", "Bebyggelsestruktur")
        rings = [symbol.symbolLayer(0) for symbol in symbols]
        self.assertEqual(rings[0].fillColor().alpha(), 0)  # ringen är ihålig
        sizes = [r.size() for r in rings]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertLess(symbols[0].symbolLayer(1).size(), sizes[0])  # pricken i mitten

    def test_areas_have_a_soft_edge_of_plain_lines(self):
        symbol = self.overview(UI + "polygon", "Bebyggelsestruktur")[0]
        lines = [symbol.symbolLayer(i) for i in range(1, symbol.symbolLayerCount())]
        self.assertEqual(len(lines), len(styles.SOFT_EDGE))
        self.assertEqual([layer.layerType() for layer in lines], ["SimpleLine"] * len(lines))
        widths = [layer.width() for layer in lines]
        alphas = [layer.color().alpha() for layer in lines]
        self.assertEqual(widths, sorted(widths, reverse=True))  # bred och svag ytterst
        self.assertEqual(alphas, sorted(alphas))
        self.assertFalse(any(layer.useCustomDashPattern() for layer in lines))
        text = self.layers[UI + "polygon"].exportSldStyleV3(QgsSldExportContext()).toString()
        self.assertNotIn("GraphicStroke", text)
        self.assertNotIn("stroke-dasharray", text)
        self.assertIn("stroke-opacity", text)

    def test_zoomed_in_the_band_and_arrowhead_shrink(self):
        level = self.theme(UI + "line", "Kommunikation").children()[1]  # kommunal
        overview, zoomed = level.children()
        self.assertTrue(overview.isScaleOK(250_000))
        self.assertFalse(overview.isScaleOK(20_000))
        self.assertTrue(zoomed.isScaleOK(20_000))
        self.assertFalse(zoomed.isScaleOK(250_000))
        big, small = overview.symbol(), zoomed.symbol()
        self.assertLess(small.symbolLayer(0).width(), big.symbolLayer(0).width() / 2)
        head = lambda rule: rule.children()[0].symbol().symbolLayer(0).subSymbol().size()  # noqa: E731
        self.assertLess(head(zoomed), head(overview) / 2)
        self.assertAlmostEqual(head(overview), big.symbolLayer(0).width() * styles.ARROW_FACTOR, places=1)
        text = self.layers[UI + "line"].exportSldStyleV3(QgsSldExportContext()).toString()
        self.assertIn("<se:MaxScaleDenominator>50000</se:MaxScaleDenominator>", text)
        self.assertIn("<se:MinScaleDenominator>50000</se:MinScaleDenominator>", text)

    def test_the_level_filter_keeps_its_parentheses_in_the_sld(self):
        text = self.layers[UI + "line"].exportSldStyleV3(QgsSldExportContext()).toString()
        root = ET.fromstring(text)
        filters = list(root.iter(OGC + "Filter"))
        self.assertTrue(filters)
        for element in filters:
            top = element[0]
            self.assertEqual(top.tag, OGC + "And")  # tema OCH (nivå ELLER nivå)
        self.assertNotIn("<ogc:Function", text)
        self.assertNotIn("ElseFilter", text)

    def test_objects_without_level_are_drawn_as_local(self):
        self.assertIn('"sambandsniva_varde" IS NULL', symbology.level_filter(styles.DEVELOPMENT_LEVELS[-1]))
        self.assertTrue(symbology.level_filter(styles.DEVELOPMENT_LEVELS[0]).startswith("("))


class ArrowDialogTests(PlanCase):
    def lookups(self):
        from rita_oversiktsplan.core import model as m
        from rita_oversiktsplan.core.storage import GeoPackageStorage
        return {lookup.name: GeoPackageStorage(self.path).read_lookup(lookup) for lookup in m.LOOKUPS}

    def make(self, suffix="line", current=None):
        from rita_oversiktsplan.core import model as m
        from rita_oversiktsplan.gui.assign_dialog import AssignDialog
        return AssignDialog(suffix, self.lookups(), current,
                            next(c for c in m.CATEGORIES if c.key == "utvecklingsinriktning"))

    def test_lines_get_the_arrow_boxes_with_the_theme_as_default(self):
        dialog = self.make()
        self.assertTrue(dialog.form.isRowVisible(dialog.arrows))
        dialog.complement.setCurrentIndex(dialog.complement.findData("Grön- och blåstruktur"))
        self.assertTrue(dialog.arrow_end.isChecked())
        self.assertTrue(dialog.arrow_start.isChecked())
        self.assertIsNone(dialog.assignment().values["rita_pilar"])  # följer temat
        dialog.complement.setCurrentIndex(dialog.complement.findData("Kommunikation"))
        self.assertFalse(dialog.arrow_start.isChecked())

    def test_ticking_the_boxes_stores_the_choice(self):
        dialog = self.make()
        dialog.complement.setCurrentIndex(dialog.complement.findData("Kommunikation"))
        dialog.arrow_start.click()
        self.assertEqual(dialog.assignment().values["rita_pilar"], "båda")
        dialog.arrow_end.click()
        self.assertEqual(dialog.assignment().values["rita_pilar"], "start")
        dialog.arrow_start.click()
        self.assertEqual(dialog.assignment().values["rita_pilar"], "ingen")

    def test_a_stored_choice_is_shown_again(self):
        dialog = self.make(current={"kompletterandeInnehallstyp": "Kommunikation", "rita_pilar": "båda"})
        self.assertTrue(dialog.arrow_end.isChecked())
        self.assertTrue(dialog.arrow_start.isChecked())

    def test_areas_and_points_have_no_arrow_boxes(self):
        for suffix in ("polygon", "point"):
            dialog = self.make(suffix)
            self.assertFalse(dialog.form.isRowVisible(dialog.arrows), suffix)
            self.assertNotIn("rita_pilar", dialog.assignment().values)

    def test_the_arrow_field_is_the_plugins_own_and_not_exported(self):
        from rita_oversiktsplan.core import export_lm
        from qgis.core import QgsGeometry, QgsVectorLayerUtils
        layer = self.layers[UI + "line"]
        self.assertGreaterEqual(layer.fields().indexOf("rita_pilar"), 0)
        self.assertLess(self.layers[UI + "polygon"].fields().indexOf("rita_pilar"), 0)
        layer.startEditing()
        values = {layer.fields().indexOf("innehallstyp_varde"): "Utvecklingsinriktning",
                  layer.fields().indexOf("rita_pilar"): "båda"}
        layer.addFeature(QgsVectorLayerUtils.createFeature(
            layer, QgsGeometry.fromWkt("LINESTRING(580000 6580000, 581000 6581000)"), values))
        self.assertTrue(layer.commitChanges())
        collection, _ = export_lm.export(project.active_plan_group(self.project))
        self.assertEqual(sum(1 for f in collection["features"] if f["properties"]["feature:typ"] == "innehallOP"), 1)
        self.assertNotIn("rita_pilar", export_lm.dumps(collection))
        self.assertNotIn("båda", export_lm.dumps(collection))


class MapTests(PlanCase):
    def test_existing_land_use_covers_eighty_percent_without_an_edge(self):
        category = self.layers[MVA].renderer().categories()[0]
        symbol = category.symbol()
        self.assertEqual(symbol.symbolLayerCount(), 1)
        self.assertEqual(symbol.symbolLayer(0).color().alpha(), styles.LAND_USE_ALPHA)

    def test_content_shows_its_name(self):
        for table in (MVA, UI + "line", "innehall_op_klimatrelateradrisk_point"):
            layer = self.layers[table]
            self.assertTrue(layer.labelsEnabled(), table)
            self.assertEqual(layer.labeling().settings().fieldName, "namn")
        self.assertTrue(self.layers[MVA].labeling().settings().scaleVisibility)
        self.assertEqual(self.layers[MVA].labeling().settings().minimumScale, styles.LABEL_SCALE)
        self.assertFalse(self.layers[UI + "point"].labeling().settings().scaleVisibility)  # schemat: alltid

    def test_everything_is_visible_at_every_scale(self):
        for table in ("innehall_op_klimatrelateradrisk_point", "innehall_op_klimatrelateradrisk_line", MVA,
                      UI + "line", UI + "point"):
            self.assertFalse(self.layers[table].hasScaleBasedVisibility(), table)

    def test_points_and_lines_get_smaller_in_steps_further_out(self):
        for table, size in (("innehall_op_klimatrelateradrisk_point", lambda s: s.size()),
                            ("innehall_op_klimatrelateradrisk_line", lambda s: s.symbolLayer(0).width()),
                            ("innehall_op_markochvattenanvandning_line", lambda s: s.symbolLayer(0).width())):
            renderer = self.layers[table].renderer()
            root = renderer.rootRule()
            steps = root.children()[0].children()
            self.assertEqual([(s.maximumScale(), s.minimumScale()) for s in steps],
                             [(inner, outer) for inner, outer, _ in styles.SIZE_STEPS], table)
            sizes = [size(s.symbol()) for s in steps]
            self.assertEqual(sizes, sorted(sizes, reverse=True), table)
            self.assertGreaterEqual(min(sizes), min(styles.MIN_LINE_WIDTH, styles.MIN_MARKER_SIZE), table)

    def test_labels_and_scales_reach_the_sld(self):
        text = self.layers[MVA].exportSldStyleV3(QgsSldExportContext()).toString()
        self.assertIn("<se:TextSymbolizer>", text)
        self.assertIn("<se:MaxScaleDenominator>100000</se:MaxScaleDenominator>", text)
        self.assertIn('fill-opacity">0.8<', text)


class RiksintressenMapTests(PlanCase):
    POSITION = "innehall_op_riksintressenop_polygon"
    SOURCE = "innehall_op_riksintressen_polygon"

    def test_the_municipalitys_position_has_a_band_inside_the_edge_and_a_very_faint_fill(self):
        renderer = self.layers[self.POSITION].renderer()
        root = renderer.rootRule()
        steps = root.children()[0].children()
        self.assertEqual(len(steps), len(styles.BAND_STEPS))
        symbol = steps[0].symbol()
        fill, band, edge = symbol.symbolLayer(0), symbol.symbolLayer(1), symbol.symbolLayer(2)
        self.assertEqual(fill.color().alpha(), styles.BAND_FILL_ALPHA)
        self.assertGreater(band.offset(), 0)  # positiv förskjutning = innanför kanten
        self.assertEqual(band.color().alpha(), styles.BAND_ALPHA)
        self.assertAlmostEqual(band.offset() * 2, band.width())
        self.assertEqual(edge.color().alpha(), 255)

    def test_the_band_gets_narrower_further_out(self):
        renderer = self.layers[self.POSITION].renderer()
        root = renderer.rootRule()
        steps = root.children()[0].children()
        widths = [step.symbol().symbolLayer(1).width() for step in steps]
        self.assertEqual(widths, sorted(widths, reverse=True))
        self.assertEqual([(s.maximumScale(), s.minimumScale()) for s in steps],
                         [(inner, outer) for inner, outer, _, _ in styles.BAND_STEPS])
        self.assertEqual(root.children()[-1].filterExpression(), '"innehallstyp_varde" IS NULL')

    def test_the_name_follows_the_edge_in_both_riksintresse_groups(self):
        for table in (self.POSITION, self.SOURCE):
            labeling = self.layers[table].labeling()
            settings = labeling.settings()
            self.assertEqual(settings.placement, Qgis.LabelPlacement.PerimeterCurved, table)
            self.assertTrue(settings.isExpression, table)  # namn – vilket riksintresse

    def test_the_riksintressen_have_the_band_and_their_dashed_edge(self):
        renderer = self.layers[self.SOURCE].renderer()
        root = renderer.rootRule()
        steps = root.children()[0].children()
        self.assertEqual(len(steps), len(styles.BAND_STEPS))
        symbol = steps[0].symbol()
        self.assertEqual(symbol.symbolLayer(0).color().alpha(), styles.BAND_FILL_ALPHA)
        self.assertTrue(symbol.symbolLayer(2).useCustomDashPattern())

    def test_the_plan_area_has_no_name_in_the_map(self):
        self.assertFalse(self.layers["innehall_op_plangeometri"].labelsEnabled())

    def test_the_label_says_which_riksintresse_it_is(self):
        labeling = self.layers[self.POSITION].labeling()
        settings = labeling.settings()
        self.assertTrue(settings.isExpression)
        expression = QgsExpression(settings.fieldName)
        context = QgsExpressionContext()
        for name, expected in (("Vänern", "Vänern – Turism och rörligt friluftsliv"),
                               (None, "Turism och rörligt friluftsliv")):
            feature = QgsFeature(self.layers[self.POSITION].fields())
            feature["namn"] = name
            feature["innehallstyp_varde"] = "Turism och rörligt friluftsliv"
            context.setFeature(feature)
            self.assertEqual(expression.evaluate(context), expected)

    def test_every_overlay_area_has_the_band_and_its_name_along_the_edge(self):
        layer = self.layers["innehall_op_klimatrelateradrisk_polygon"]
        labeling = layer.labeling()
        self.assertEqual(labeling.settings().placement, Qgis.LabelPlacement.PerimeterCurved)
        self.assertEqual(labeling.settings().fieldName, "namn")
        root = layer.renderer().rootRule()
        self.assertEqual(len(root.children()[0].children()), len(styles.BAND_STEPS))

    def test_the_band_reaches_the_sld_as_an_offset_line(self):
        text = self.layers[self.POSITION].exportSldStyleV3(QgsSldExportContext()).toString()
        self.assertIn("PerpendicularOffset", text)
        self.assertIn("<se:MinScaleDenominator>150000</se:MinScaleDenominator>", text)


class GeoServerTests(unittest.TestCase):
    QGIS_SLD = """<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.1.0" xmlns:ogc="http://www.opengis.net/ogc"
 xmlns:se="http://www.opengis.net/se"><NamedLayer><UserStyle><se:FeatureTypeStyle><se:Rule>
<se:LineSymbolizer><se:Stroke><se:SvgParameter name="stroke">#e6781e</se:SvgParameter></se:Stroke></se:LineSymbolizer>
<se:LineSymbolizer><se:VendorOption name="placement">lastPoint</se:VendorOption><se:Stroke><se:GraphicStroke>
<se:Graphic><se:Mark><se:WellKnownName>triangle</se:WellKnownName></se:Mark><se:Size>29</se:Size>
<se:Rotation><ogc:Literal>90</ogc:Literal></se:Rotation></se:Graphic></se:GraphicStroke></se:Stroke></se:LineSymbolizer>
<se:LineSymbolizer><se:VendorOption name="placement">firstPoint</se:VendorOption><se:Stroke><se:GraphicStroke>
<se:Graphic><se:Mark><se:WellKnownName>triangle</se:WellKnownName></se:Mark><se:Size>29</se:Size>
<se:Rotation><ogc:Literal>270</ogc:Literal></se:Rotation></se:Graphic></se:GraphicStroke></se:Stroke></se:LineSymbolizer>
</se:Rule></se:FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>"""

    def test_arrowheads_become_points_at_the_line_ends(self):
        root = ET.fromstring(sld.for_geoserver(self.QGIS_SLD))
        rule = next(root.iter(SE + "Rule"))
        self.assertEqual([child.tag for child in rule], [SE + "LineSymbolizer", SE + "PointSymbolizer",
                                                         SE + "PointSymbolizer"])
        ends = [p.find(f"{SE}Geometry/{OGC}Function").get("name") for p in rule.iter(SE + "PointSymbolizer")]
        self.assertEqual(ends, ["endPoint", "startPoint"])
        angles = [p.find(f"{SE}Graphic/{SE}Rotation/{OGC}Add/{OGC}Function").get("name")
                  for p in rule.iter(SE + "PointSymbolizer")]
        self.assertEqual(angles, ["endAngle", "startAngle"])
        offsets = [p.find(f"{SE}Graphic/{SE}Rotation/{OGC}Add/{OGC}Literal").text
                   for p in rule.iter(SE + "PointSymbolizer")]
        self.assertEqual(offsets, ["90", "270"])
        self.assertNotIn("VendorOption", sld.for_geoserver(self.QGIS_SLD))
        self.assertIn("<ogc:PropertyName>geom</ogc:PropertyName>", sld.for_geoserver(self.QGIS_SLD))

    def test_a_style_without_arrowheads_is_unchanged_in_content(self):
        plain = self.QGIS_SLD.split("<se:LineSymbolizer><se:VendorOption")[0] + \
            "</se:Rule></se:FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>"
        root = ET.fromstring(sld.for_geoserver(plain))
        self.assertEqual([c.tag for c in next(root.iter(SE + "Rule"))], [SE + "LineSymbolizer"])


class HideLabelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.plugin = classFactory(FakeIface())
        self.plugin.initGui()
        self.addCleanup(self.plugin.unload)
        self.addCleanup(QgsProject.instance().clear)

    def load(self, name):
        path = geopackage.create_geopackage(Path(self.tmp.name) / name, PLAN)
        layers = project.load_plan(path, QgsProject.instance())
        self.plugin.refresh_tools()  # sker annars via layersAdded
        return layers

    def test_the_button_hides_and_shows_the_names_in_every_plan(self):
        layers = self.load("a.gpkg")
        button = self.plugin.toolbar.act_hide_labels
        self.assertTrue(button.isEnabled())
        button.setChecked(True)
        self.assertFalse(layers[MVA].labelsEnabled())
        self.assertFalse(layers[UI + "line"].labelsEnabled())
        self.assertIn("dolda", button.toolTip())
        other = self.load("b.gpkg")  # en plan som läses in medan texterna är dolda
        self.assertFalse(other[MVA].labelsEnabled())
        button.setChecked(False)
        self.assertTrue(layers[MVA].labelsEnabled())
        self.assertTrue(other[MVA].labelsEnabled())


class ExportSldTests(unittest.TestCase):
    def test_the_menu_entry_writes_a_style_file_per_content_layer(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        iface = FakeIface()
        plugin = classFactory(iface)
        plugin.initGui()
        self.addCleanup(plugin.unload)
        path = geopackage.create_geopackage(Path(tmp.name) / "op.gpkg", PLAN)
        project.load_plan(path, QgsProject.instance())
        self.addCleanup(QgsProject.instance().clear)
        folder = Path(tmp.name) / "sld"
        folder.mkdir()
        with mock.patch.object(type(plugin), "_ask_folder", return_value=str(folder)):
            written = plugin.export_sld()
        self.assertTrue(written)
        line = (folder / (UI + "line.sld")).read_text(encoding="utf-8")
        self.assertIn("endPoint", line)
        self.assertNotIn('name="placement"', line)
        self.assertTrue((folder / (MVA + ".sld")).is_file())


if __name__ == "__main__":
    unittest.main()
