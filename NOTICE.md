# Källor och material från andra

Rita Översiktsplan är licensierat under GPL-2.0-or-later (se [LICENSE](LICENSE)). Följande material kommer från andra och
har egna villkor. Kontrollera villkoren själv om du sprider eller bygger vidare på repot.

| Material | Var | Källa | Villkor |
|---|---|---|---|
| ÖP-katalogen (version 2.2) | `rita_oversiktsplan/data/opkatalog.json` | Boverket, [ÖP-katalogen](https://www.boverket.se/sv/om-boverket/oppna-data/api-for-op-katalogen/) (API `https://api.boverket.se/opmodell`) | CC0 enligt Boverkets användarvillkor för API-tjänsten (punkt 5.3); källa anges i filen. Boverket ansvarar inte för pluginet. |
| Tabell- och kolumnnamn i datamodellen | `rita_oversiktsplan/core/model.py` | Boverket, [GIS-databasmodell för ÖP-modellen](https://www.boverket.se/sv/om-boverket/oppna-data/gis-databas-op-modell/) 0.3 | Öppna data. Pluginet bygger tabellerna själv; Boverkets fil följer inte med. |
| Färgkoder för markanvändning | `rita_oversiktsplan/core/styles.py` (`FARGER`) | Stilbiblioteket *Detaljplaner (Bfs 2020:6)*, [QGIS Hub, stil 238](https://hub.qgis.org/styles/238/), via Rita Detaljplan | CC0 1.0. |
| Kommunlista med kommunkoder | `rita_oversiktsplan/data/kommuner.json` | SCB, Regionala indelningar (<https://api.scb.se>) | SCB:s öppna statistik; källa anges i filen. |
| Vägledningstexter i utkastet till planhandling | `exempel/Planhandling_mall_ÖP-katalogen_2.2.docx` | Boverket, ÖP-katalogen 2.2 (vägledning och beskrivningar) | CC0, som katalogen ovan. |
| Ikoner i verktygsfältet (öppna, uppgifter, penna, diskett, markera, avmarkera, kopiera, exportera, checka ut/in, ikonen för planhandlingen) | `rita_oversiktsplan/icons/` | Rita Detaljplan (samma upphovsperson) | GPL-2.0-or-later, som pluginet. |
| Lantmäteriets format för översiktsplan och geometri | `rita_oversiktsplan/core/export_lm.py` | Lantmäteriet, JSON-schemana *oversiktsplan-2.0* och *geometri-2.0.1* (`namespace.lantmateriet.se`) | Exporten följer schemana; schemafilerna följer inte med i repot. |
| Lantmäteriets regler (OP-JSON-…, ÖP-X…) | `rita_oversiktsplan/core/rules.py` | Lantmäteriet, objekttypskatalog och dataproduktspecifikation för översiktsplan, 1.0 test 4 ([sidan om översiktsplan](https://www.lantmateriet.se/sv/nationella-geodataplattformen/datamangder/oversiktsplan/)) | Reglerna är omskrivna som kod; dokumenten följer inte med i repot. |
| Kommunens yta (hämtas när man skapar en plan med rutan ikryssad) | `rita_oversiktsplan/core/kommunyta.py` | Lantmäteriet, kommunytor, via länsstyrelsernas nationella visningstjänst `ext-geodata-nationella-visning.lansstyrelsen.se` | Inga data följer med i pluginet; lagernummer och fältnamn är inskrivna. Villkoren för datan är Lantmäteriets. |
| Topografi 10 och Marktäcke (läses ur filer som användaren själv laddar ner) | `rita_oversiktsplan/core/topografi.py` | Lantmäteriet, *Topografi 10 Nedladdning, vektor* och *Marktäcke Nedladdning, vektor* (Geotorget); objekttyper och ändamål enligt Lantmäteriets dokumentation av Topografi 10 | Inga data följer med i pluginet. Ange Lantmäteriet som källa när planen sprids (Marktäcke: CC BY 4.0 enligt Lantmäteriets STAC-katalog). |
| Färger för markytorna | `rita_oversiktsplan/core/styles.py` (`TOPOGRAFI10`) | Lantmäteriets stilfil för QGIS *Topografi10_vektor_220825.qlr* (Geotorget, dokumentationen för Topografi 10) | Färgvärdena är återgivna; stilfilen följer inte med. |
| Riksintressen (hämtas när man använder funktionen) | `rita_oversiktsplan/core/riksintressen.py` | Boverket, karttjänsten *Riksintressen* (`gis2.boverket.se/arcgis/rest/services/Riksintressen___Februari_2025_WMS/MapServer`), med data från bland andra Naturvårdsverket, Riksantikvarieämbetet, Trafikverket och länsstyrelserna | Inga data följer med i pluginet; lagernummer och fältnamn är inskrivna. Villkoren för datan är respektive myndighets. |
| Text i bannrarna | `docs/images/banner-*.svg`, `social-preview.png` | Typsnitten Archivo och IBM Plex Mono ([Google Fonts](https://fonts.google.com/)) | SIL Open Font License 1.1. Texten är omvandlad till konturer; typsnittsfilerna följer inte med i repot. |

Pluginet är **inte** en officiell produkt från Lantmäteriet eller Boverket och har ingen koppling till dem utöver att det
följer deras öppna specifikationer.
