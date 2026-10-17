# Datamodell – Rita Översiktsplan

Pluginet lagrar en översiktsplan i en GeoPackage-fil med samma tabeller och kolumner som Boverkets
[GIS-databasmodell för ÖP-modellen](https://www.boverket.se/sv/om-boverket/oppna-data/gis-databas-op-modell/),
version **0.3**. Den versionen är synkad med test 4_1 av Lantmäteriets
[nationella specifikation för översiktsplan](https://www.lantmateriet.se/sv/nationella-geodataplattformen/datamangder/oversiktsplan/).
Värdena kommer från Boverkets [ÖP-katalog](https://www.boverket.se/sv/om-boverket/oppna-data/api-for-op-katalogen/),
version **2.2**. Modellen finns i koden i `rita_oversiktsplan/core/model.py`.

## Tabellerna

| Tabell | Innehåll |
|---|---|
| `oversiktsplan` | Planens uppgifter, en rad (kommun, titel, planhändelse, datum, digitalt ursprung) |
| `innehall_op_<typ>_polygon`, `_line`, `_point` | Planens innehåll, ett lager per innehållstyp och geometrityp |
| `innehall_op_plangeometri`, `innehall_op_omrade` | Plangeometri och områden (bara ytor) |
| `*_lookup` | Värden ur ÖP-katalogen: värde, värdets id, grupp, gruppens id och katalogversion |
| `dokumentreferens_op`, `dokumentavsnitt`, `avsnittsbokmärke` | Hänvisningar till planhandlingen och dess avsnitt (bokmärken i Word) |
| `oversiktsplan_underlag`, `oversiktsplan_underlag_underlag` | Planens underlag (fliken *Underlag* i Planens uppgifter): en rad per underlagstyp med eget `underlag_id`, kopplad till sina dokument i `dokumentreferens_op` (kortnamnet är underlagstypen). Planens `underlag_id` lämnas tom, eftersom den bara kan peka på ett underlag (tolkning) |
| `innehall_op_beror_annat_innehall`, `innehall_op_extern_referens_ri` | Kopplingar mellan innehåll och till riksintressen |
| `beslut_op` | Beslut om planen (*beslutOP* i Lantmäteriets specifikation): diarienummer, beslutande organisation och instans (kommunfullmäktige), datum fattat, överklagat och laga kraft, arkividentitet. `oversiktsplan.beslut` pekar på antagandebeslutets objektidentitet. **Tillägg**: Boverkets mall har ingen tabell för beslut, bara kolumnen `beslut` |
| `rita_oversiktsplan_meta` | Pluginets egen tabell: schemaversion, databasmodell, katalogversion, koordinatsystem och standardvärdena för nytt innehåll (nycklar som börjar på `standard_`) |
| `rita_otilldelad_yta`, `rita_otilldelad_linje`, `rita_otilldelad_punkt` | Pluginets egna tabeller: geometri som ritats men ännu inte fått innehåll. Ett objekt flyttas till rätt innehållslager när det tilldelas innehåll. Följer inte med i en leverans |

**I en PostGIS-databas** (se [Användarhandledning](anvandning.md)) har schemat samma tabeller, med en kolumn `plan`
(planens id) i varje tabell, även uppslagstabellerna och metadatatabellen, så att flera planer kan dela schemat och
ändå ha var sin katalogversion. `fid` är en `serial`-kolumn och geometrin heter `geom` (SRID 3006). PostgreSQL tillåter högst 63 tecken i ett tabellnamn, så tabellerna för *Särskilt värdefull kulturmiljö* heter `innehall_op_sarskiltvardefullkulturmiljo_…` i databasen (i GeoPackage behålls Boverkets längre namn). Tabellen
`rita_oversiktsplan_schema` har schemats version. Låset vid utcheckning är en rad `checkout` i
`rita_oversiktsplan_meta`.

**Planhandlingen** (se [Användarhandledning](anvandning.md)) sparas i Boverkets dokumenttabeller:
`dokumentreferens_op` får en rad för Word-dokumentet (namn, länk till filen, `dokumentreferens_id`),
`avsnittsbokmärke` en rad per bokmärke (namnet och rubriken), och `dokumentavsnitt` en rad per koppling mellan ett
avsnitt och ett objekt (avsnittstyp, bokmärke, dokumentet och objektets `objektidentitet`). Objektets `dokument_id`
sätts till dess objektidentitet, och samma värde står i `dokumentavsnitt.dokument_id`. Det är en tolkning: mallen
beskriver inte kolumnen närmare. Kopplingar till hela planen gäller raden i `oversiktsplan`.

**Innehåll utan geometri** (till exempel bostadsförsörjning som bara beskrivs i text) sparas i gruppens ytlager
(`…_polygon`) med tom geometri. Geometrin är frivillig för innehåll i specifikationen, men mark- och
vattenanvändningen ska enligt föreskrifterna vara lägesbestämd och kan inte sakna geometri.

En GeoPackage innehåller en översiktsplan. Därför har innehållslagren ingen kolumn som pekar på planen: kopplingen
följer av att de ligger i samma fil.

## Var pluginet avviker från Boverkets mall

Boverkets mall har några ojämnheter. Pluginet rättar dem så här:

- **Nyckel, geometri och koordinatsystem.** Alla tabeller har `fid` som nyckel och `geom` som geometrikolumn, och
  alla lager ligger i samma koordinatsystem: SWEREF 99 TM (EPSG:3006, som i mallen och förvalt) eller en lokal
  SWEREF 99-zon (EPSG:3007–3018), som Lantmäteriets specifikation också tillåter. Det står i metadatan (`epsg`). I mallen har några tabeller `OBJECTID` och `Shape`, och lagret
  Plangeometri ligger i Web Mercator (EPSG:3857).
- **Kommunnamn.** `oversiktsplan` har även kolumnen `kommunnamn`, eftersom specifikationen kräver den.
- **Typer.** Datum lagras som datum, ja/nej-fält som booleska fält, och `digitalt_ursprung` som ja/nej (text i
  mallen). Presentationsskalan är ett heltal, som i specifikationen.
- **Borttaget.** Restkolumnerna `dokument_id1`, `planhandelse_datum1` och `GlobalID` finns inte med. Inte heller
  `anvandningsstatus`, som togs bort ur ÖP-katalogen i version 2.0, eller `texttyp_lookup`, som ersatts av
  `avsnittstyp_varde_lookup`.
- **Uppslagstabellerna** har samma kolumner överallt och fylls med värden ur den medföljande ÖP-katalogen 2.2. Mallen
  har värden ur version 2.0, med radbrytningar i vissa värden och id:n i olika format.
- **Behållet som i mallen:** tabellnamnet `avsnittsbokmärke` (med ä) och kolumnnamnen `beror_annat_innehal_uuid` och
  `dokumentreferns_id` (felstavade i mallen). De behålls för att filen ska stämma med Boverkets modell.

## ÖP-katalogen i pluginet

Pluginet har en kopia av ÖP-katalogen i `rita_oversiktsplan/data/opkatalog.json`. Den hämtas från Boverkets öppna API
med `python tools/update_opkatalog.py`. Text och bild i API:et omfattas av CC0 enligt Boverkets användarvillkor.

När en plan skapas kopieras katalogens värden in i planens uppslagstabeller. Planen behåller sedan den
katalogversionen, även om pluginet senare får en nyare katalog. Boverket säger att en plan får fortsätta i den
katalogversion som arbetet påbörjades i.
