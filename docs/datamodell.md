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
| `rita_oversiktsplan_meta` | Pluginets egen tabell: schemaversion (4 sedan 0.1.3: + `precisering` i plangeometrin), databasmodell, katalogversion, koordinatsystem och standardvärdena för nytt innehåll (nycklar som börjar på `standard_`) |
| `rita_otilldelad_yta`, `rita_otilldelad_linje`, `rita_otilldelad_punkt` | Pluginets egna tabeller: geometri som ritats men ännu inte fått innehåll. Ett objekt flyttas till rätt innehållslager när det tilldelas innehåll. Följer inte med i en leverans |

**Två slags UUID.** Varje objekt (planen, varje innehåll, beslutet) har en egen `objektidentitet`: ett UUID som
pluginet sätter när objektet skapas eller tilldelas, unikt för just det objektet. Det syns i formuläret och
attributtabellen men går inte att ändra, eftersom exporten, kopplingarna och planhandlingens bokmärken hänvisar till det.
ÖP-katalogens UUID är något annat: `vardereferens` (och `gruppreferens`) i uppslagstabellerna, som identifierar ett
*värde* i katalogen, till exempel *Bostadsförsörjning*. Det är samma för alla objekt med det värdet, och följer med i
exporten som `innehallstyp.vardereferens`.

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
- **Plangeometri.** `innehall_op_plangeometri` har kolumnerna `objektidentitet` och `vertikal_avgransning`, som
  mallen saknar men specifikationen har för allt innehåll. Precis som i mallen har den `precisering` (från schema 4;
  tidigare saknades den av misstag) men inte kompletterande innehållstyp. *Område* har varken precisering eller
  kompletterande innehållstyp, som i mallen.
- **Typer.** Datum lagras som datum, ja/nej-fält som booleska fält, och `digitalt_ursprung` som ja/nej (text i
  mallen). Presentationsskalan är ett heltal, som i specifikationen. I `dokumentreferens_op` har mallen fälten
  `identitet`, `namespace` och `lank` som heltal (MEDIUMINT); här är de text, eftersom en länk är en webbadress och
  identiteten i specifikationen är en teckensträng.
- **Borttaget.** Restkolumnerna `dokument_id1`, `planhandelse_datum1` och `GlobalID` finns inte med. Inte heller
  `anvandningsstatus`, som togs bort ur ÖP-katalogen i version 2.0, eller `texttyp_lookup`, som ersatts av
  `avsnittstyp_varde_lookup`.
- **Uppslagstabellerna** har samma kolumner överallt och fylls med värden ur den medföljande ÖP-katalogen 2.2. Mallen
  har värden ur version 2.0, med radbrytningar i vissa värden och id:n i olika format.
- **Jämförelse med mallfilen.** Pluginets fil har jämförts med Boverkets `databasmodell_op_0.3.gpkg` (hämtad
  2026-10-19), tabell för tabell och kolumn för kolumn. Alla mallens tabeller finns (utom `texttyp_lookup`, se
  ovan), med samma kolumnnamn. Skillnaderna är de som står i den här listan.
- **Behållet som i mallen:** tabellnamnet `avsnittsbokmärke` (med ä) och kolumnnamnen `beror_annat_innehal_uuid` och
  `dokumentreferns_id` (felstavade i mallen). De behålls för att filen ska stämma med Boverkets modell.

## ÖP-katalogen i pluginet

Pluginet har en kopia av ÖP-katalogen i `rita_oversiktsplan/data/opkatalog.json`. Den hämtas från Boverkets öppna API
med `python tools/update_opkatalog.py`. Text och bild i API:et omfattas av CC0 enligt Boverkets användarvillkor.

När en plan skapas kopieras katalogens värden in i planens uppslagstabeller. Planen behåller sedan den
katalogversionen, även om pluginet senare får en nyare katalog. Boverket säger att en plan får fortsätta i den
katalogversion som arbetet påbörjades i.

## Pluginets eget fält i utvecklingsinriktningens linjer

`innehall_op_utvecklingsinriktning_line` har kolumnen `rita_pilar` (från schema 4), som inte finns i Boverkets mall:
pilspetsarna i kartan (*slut*, *start*, *båda* eller *ingen*; tomt betyder temats standard). Den följer inte med i
exporten till Lantmäteriet.

## Kopplingar (0.1.1)

- **Berör annat innehåll:** innehållets `beror_annat_innehall_id` (ett UUID som pluginet sätter första gången) pekar på
  rader i `innehall_op_beror_annat_innehall`, en per berört innehåll, med det berördas objektidentitet i
  `beror_annat_innehal_uuid` (mallens stavning).
- **Riksintressets id** sparas i `objektidentitet_ri` i lagren för riksintressen.
- **Beslut (från 0.1.5):** antagandebeslutet (planens `beslut`) påverkar bara planen. Innehållets `beslut` pekar på en
  ändrings beslut. Äldre planer där innehållet har antagandebeslutets id exporteras utan det (OP-JSON-005).

## Utbyggnadsordning (0.1.5)

Planens etapper står i meta-tabellen under nyckeln `utbyggnadsordning`, som JSON: en lista med `{"namn", "period"}`
i utbyggnadsordning. Innehållets fält `utbyggnadsordning` (mark- och vattenanvändning, utvecklingsinriktning) får
etappens text, `namn (period)`. Ingen ny tabell eller kolumn behövs, så schemat är oförändrat.

## Ändring av planen (0.1.5)

En ändring är en rad i `beslut_op` med rubriken *Ändring: namn*. Den pågående ändringen står i meta-tabellen:

| Nyckel | Värde |
|---|---|
| `andring_beslut` | ändringsbeslutets objektidentitet |
| `andring_paborjat` | datum påbörjat (blir innehållets `datum_paborjat`) |
| `andring_planhandelse`, `andring_planhandelse_datum` | ändringens planhändelse |

Nytt innehåll får dessa värden och `beslut` = ändringsbeslutet. Ett beslut utan datum (fattat, överklagat, laga kraft)
som inte är planens räknas som pågående och exporteras inte. När ändringen antas tas nycklarna bort.

**Hämtade riksintressen** (0.1.5) har `objektidentitet_ri` = myndighetens id och `hamtatdatum` = dagen för hämtningen.

