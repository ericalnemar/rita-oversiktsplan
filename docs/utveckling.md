# Utveckling – Rita Översiktsplan

För dig som vill köra koden, testerna eller bidra. Se även [CONTRIBUTING](../CONTRIBUTING.md).

## Köra testerna

Kräver QGIS 4.x (testat med 4.2.2). Kör testerna med QGIS egen Python (sätt `QGIS_ROOT` om QGIS ligger någon
annanstans):

```
tests\run_tests.bat
```

`tests/test_opkatalog.py`, `tests/test_branding.py` och `tests/test_release.py` går också med vanlig Python.

## Uppdatera ÖP-katalogen

```
python tools/update_opkatalog.py     # hämtar aktuell katalog från Boverkets API (kräver nätverk)
```

Skriptet skriver `rita_oversiktsplan/data/opkatalog.json`. Kör testerna efteråt: en ny katalogversion kan ha
ändrade kategorier som modellen (`core/model.py`) behöver följa.

## Utkast till planhandling

```
python tools/skapa_planhandling_mall.py   # skriver exempel/Planhandling_mall_ÖP-katalogen_<version>.docx
```

Ett Word-dokument med en rubrik för allt innehåll i den medföljande ÖP-katalogen. Kör skriptet igen när katalogen
uppdaterats. Ingen QGIS eller extra paket behövs.

## Märke och bannrar

```
python-qgis.bat tools/build_branding.py <mapp med Archivo-var.ttf och IBMPlexMono-Regular.ttf>
```

Bygger pluginikonen (Ö-märket), bannrarna i README och bilden för social preview. Typsnitten (SIL OFL 1.1) följer inte
med i repot; de finns i `github.com/google/fonts` (`ofl/archivo`, `ofl/ibmplexmono`). Kopiera sedan ikonen till
`docs/images/marken/rita-oversiktsplan.svg`.

## Bygga och ge ut en version

```
python tools/build_zip.py            # skapar dist/rita_oversiktsplan-<version>.zip
python tools/build_plugins_xml.py    # skriver plugins.xml (checkas in)
```

Versionen läses ur `rita_oversiktsplan/metadata.txt`. Så gör du en ny version: uppdatera `version` där och i
[CHANGELOG](../CHANGELOG.md), kör testerna, bygg zip-filen, generera pluginkällan, märk versionen (`git tag v0.1.0`) och lägg
zip-filen på en Release. `plugins.xml` pekar på zip-filen i Releasen, så skapa Releasen direkt efter att du pushat.

## Struktur

```
rita_oversiktsplan/    pluginet (det som installeras)
  plugin.py            meny och kommandon
  core/                logik: storage (fil eller PostGIS) och checkout (utcheckning, incheckning, lås),
                       model, opkatalog, styles, colors, planhandling (Word, bokmärken) och
                       planhandling_html (webbversionen) (ren Python),
                       geopackage (GDAL), project, symbology, content (rita, tilldela, planens uppgifter) och
                       documents (kopplingar till planhandlingen), relations (berör annat innehåll) (QGIS),
                       kommuner, archive (arkivpaket med PREMIS, ren Python), ngp_client och settings (leverans
                       till NGP; kopierade från Rita Detaljplan)
  gui/                 verktygsfältet, kartverktyget Tilldela innehåll och dialogerna: Ny översiktsplan,
                       Tilldela innehåll, Planens uppgifter, Leverans och export, arkivpaket, NGP-leverans och
                       inställningar, Om-dialogen, kommunlistan, meddelanderaden
  bookmarks/            programmet Skapa bokmärken i planhandling (eget fönster, som Tagga planbeskrivning i Rita
                       Detaljplan): session (tillståndet, utan Qt), host (planen i QGIS), main (fönstret),
                       pages (stegen), widgets och theme
  icons/               ikoner till verktygsfältet (SVG; Öppna, Uppgifter, pennan, Markera, Avmarkera, Kopiera och
                       Leverans och export är hämtade från Rita Detaljplan)
  data/                ÖP-katalogen och kommunlistan
tools/                 byggskript, hämtning av ÖP-katalogen, utkastet till planhandling, märket
exempel/               utkastet till planhandling (följer inte med zip-filen)
tests/                 enhetstester
docs/images/marken/    Rita-svitens märken: R (sviten), D (Rita Detaljplan), Ö (Rita Översiktsplan)
```

Datamodellen och var den avviker från Boverkets mall står i [Datamodell](datamodell.md). Delar av koden är hämtade
från syskonpluginet [Rita Detaljplan](https://github.com/ericalnemar/rita-detaljplan) genom kopiering, inte som ett
gemensamt bibliotek.
