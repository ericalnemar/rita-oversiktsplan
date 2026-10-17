# Ändringslogg

Formatet följer [Keep a Changelog](https://keepachangelog.com/sv/1.1.0/), versionsnumren [Semantic Versioning](https://semver.org/lang/sv/).

## Ej utgivet

## [0.1.1] – kopplingar, leverans till NGP och arkivpaket

- **Nytt: Berör annat innehåll** (knappen med två ytor och en blå streckad linje, sist i verktygsfältet). Klicka på ett
  innehåll och sedan på det innehåll det berör, till exempel en klimatrisk som berör ett bostadsområde. Klicka igen för
  att ta bort kopplingen. Det berörda visas i blått. Kopplingarna sparas i Boverkets tabell
  `innehall_op_beror_annat_innehall` och följer med i exporten som `berorAnnatInnehall`.
- **Riksintressets id:** för riksintressen (kommunens ställningstagande och enligt 3 och 4 kap. MB) finns fältet
  *Riksintressets id* i Tilldela innehåll. Det blir en extern referens (`externReferens`) i exporten.
- **Beslutet gäller innehållet:** när antagandebeslutet sparas under Planens uppgifter får allt innehåll som inte
  redan hör till ett annat beslut beslutets id, och beslutet räknar upp planen och innehållet (`paverkar`) i exporten.
- **Nytt: Leverans och export** (tidigare *Exportera*): samma kontroll och *Spara som JSON…*, och nya knappar
  **Leverera till NGP…**, **Skapa arkivpaket…** och **Inställningar…**.
- **Leverans till NGP** via Lantmäteriets Uppdatering-API, på samma sätt som i Rita Detaljplan: en fråga som säger
  vart planen skickas och hur många fel kontrollen hittade, leveransen i bakgrunden och sedan Lantmäteriets
  valideringsrapport. Efter ett valideringsfel skickas planen igen på samma mottagning. Inställningar för miljö
  (verifiering, produktion eller egen adress) och inloggning under *Insticksprogram → Rita Översiktsplan →
  Inställningar för leverans till NGP…*. **Inte provat mot Lantmäteriet**, se Kända begränsningar.
- **Arkivpaket med bevarandemetadata** enligt Boverkets specifikation för långtidsbevarande (som Boverket säger kan
  användas för översiktsplan "med mindre anpassningar"): en mapp med `oversiktsplan.xml` (planens uppgifter),
  `metadata/PREMIS.xml` (filerna med kontrollsummor, händelser och aktörer) och `content/` med planens GeoPackage,
  exportfilen, planhandlingen med bokmärken och dess webbversion, underlagens filer och de dokument du själv lägger
  till. **Kontrollera arkivpaket…** räknar om kontrollsummorna och säger om något ändrats. Pluginet gör inga filer
  till PDF/A, som i Rita Detaljplan.
- **Webbsidan [ritaplan.xyz](https://ritaplan.xyz)** är pluginets hemsida i QGIS pluginhanterare, och Om Rita
  Översiktsplan har en knapp *Webbsida*. Handledningen och felrapporter ligger kvar på GitHub.

## [0.1.0] – första utgåvan

Första förhandsversionen. **Arbete pågår med hur planen visas i kartan**: symbologin (färger, kantlinjer och
punktsymboler per innehållstyp) och presentationen i övrigt kommer att ändras.

- **Nytt: Ny översiktsplan** (*Insticksprogram → Rita Översiktsplan*), uppbyggd som Ny detaljplan i Rita
  Detaljplan. Välj kommun, titel, var planen lagras (lokal fil eller PostGIS-databas), koordinatsystem (SWEREF 99 TM
  eller en lokal SWEREF 99-zon, som Lantmäteriets specifikation tillåter), och datum då arbetet påbörjades
  (inget digitaliseringsläge: en ny översiktsplan har digitalt ursprung). Pluginet skapar en GeoPackage med samma tabeller och kolumner som Boverkets GIS-databasmodell för
  ÖP-modellen (version 0.3), fyller i planens uppgifter med ett unikt id, och lägger in planen överst i lagerpanelen:
  planens tabell, Plangeometri, Område, en undergrupp per innehållstyp med lager för yta, linje och punkt, och
  tabellerna för dokument och underlag.
- **Värden ur ÖP-katalogen 2.2.** Pluginet har en kopia av Boverkets ÖP-katalog (CC0). Innehållstyp, kompletterande
  innehållstyp, planhändelse, sambandsnivå och underlagstyp väljs i listor, och katalogens värden med id och grupp
  sparas i planens uppslagstabeller. En plan behåller sin katalogversion. `tools/update_opkatalog.py` hämtar en ny
  katalog från Boverkets API.
- **Rita först, tilldela sedan (som i Rita Detaljplan).** Knapparna *Rita yta*, *Rita linje* och *Rita punkt* ritar
  geometri utan innehåll och utan formulär; den hamnar i gruppen *Att tilldela* och syns i orange. Verktyget
  *Tilldela innehåll*: klicka på det ritade och välj grupp och innehållstyp ur ÖP-katalogen (med katalogens
  beskrivning), och det som gäller just det objektet (namn, precisering, kompletterande innehållstyp, sambandsnivå,
  utbyggnadsordning, beroende på grupp). Objektet flyttas till rätt innehållslager. Klick på tilldelat innehåll byter
  typ och behåller identiteten; ligger flera objekt på varandra väljer man i en meny. Verktyget är aktivt tills man
  väljer ett annat.
- **Nytt: Planens uppgifter** med flikarna *Planen* (titel, påbörjad, digitalt ursprung), *Planhändelse* (med valet
  att ge allt innehåll samma planhändelse), *Beslut*, *Underlag* och *Standardvärden för innehåll* (vertikal avgränsning, under
  ersättning, datum påbörjat, presentationsskala). Sparas direkt.
- **Planens underlag:** fliken *Underlag* i Planens uppgifter, ett dokument per rad med underlagstyp ur ÖP-katalogen,
  namn, länk eller fil och datum. Sparas i Boverkets tabeller `oversiktsplan_underlag`, `oversiktsplan_underlag_underlag`
  och `dokumentreferens_op` (ett underlag per underlagstyp med sina dokument). Exporten tar med dem, så felet om
  saknat underlag försvinner när minst ett finns.
- **Antagandebeslutet:** fliken *Beslut* tar diarienummer och datum då planen antogs, överklagades och fick laga kraft,
  som Boverkets föreskrifter kräver (BFS 2024:2, 2 kap. 2 §). Beslutet sparas i den nya tabellen `beslut_op` med
  uppgifterna i Lantmäteriets *beslutOP* (beslutande är kommunfullmäktige i planens kommun), och planen pekar på det.
- **Automatiskt för nytt innehåll:** objektidentitet (UUID), versionsdatum, *illustrativa gränser* (alltid ja),
  planens planhändelse med datum och standardvärdena under Planens uppgifter. Ett enskilt objekt kan ändras i
  attributformuläret.
- **Nytt: Spara** sparar redigeringarna i alla lager i projektet; redigeringen fortsätter.
- **Nytt: Skapa bokmärken i planhandling**, ett eget fönster byggt som motsvarande program för planbeskrivningen i Rita Detaljplan (samma toppfält
  med steg, färger och kort), som kopplar översiktsplanens textavsnitt (Word) till planens innehåll enligt Boverkets
  instruktion för texthantering. *Filer*: planen är den aktiva i QGIS, välj eller dra dit planhandlingen. *Avsnitt*:
  varje rubrik blir ett avsnitt med en föreslagen avsnittstyp ur ÖP-katalogen och skälet till förslaget; granska,
  byt typ eller välj att inte skapa bokmärke. *Koppling*: klicka på innehållet i en karta, kryssa i en lista, hämta det som är
  markerat i QGIS, koppla till hela planen eller skapa nytt innehåll utan geometri; listan visar också hur många
  avsnitt varje objekt är kopplat till. *Kontroll och spara*: fel, varningar (till exempel mark- och vattenanvändning
  som inte är kopplad till något avsnitt) och raderna som sparas; spara ger en kopia med bokmärken med ett beständigt
  Word-bokmärke per avsnitt (originalet ändras aldrig) och kopplingarna i `dokumentreferens_op`, `avsnittsbokmärke` och
  `dokumentavsnitt`, och en översikt kan sparas som CSV. En kopia med bokmärken som öppnas igen behåller sina bokmärken och
  kopplingar. Fönstret låser inte QGIS.
- **Webbversion av planhandlingen.** När kopian med bokmärken sparas kan en HTML-sida sparas bredvid den (rutan är
  ikryssad från början): rubriker, stycken, fet och kursiv stil, länkar, listor och tabeller, och varje avsnitt som
  `<section>` med bokmärket som `id` och avsnittstypen i `data-avsnittstyp`, så att en webbkarta kan länka från ett
  objekt till rätt stycke (`planhandling_bokmarken.html#op_…`). Dokumentets titel blir `<h1>` och Rubrik 1–3 blir
  `<h2>`–`<h4>`. Bilder ersätts med sin alternativtext och Words innehållsförteckning hoppas över.
- **Varning för fel dokument:** öppnas en planhandling utan bokmärken i en plan som redan har kopplingar till en
  kopia med bokmärken, säger Skapa bokmärken i planhandling det och erbjuder att öppna kopian i stället (annars får avsnitten nya
  bokmärken och de gamla kopplingarna ersätts).
- **Utkast till planhandling** med en rubrik för allt innehåll i ÖP-katalogen 2.2, katalogens vägledning och plats
  för kommunens text: `exempel/Planhandling_mall_ÖP-katalogen_2.2.docx` (skapas med `tools/skapa_planhandling_mall.py`). Att börja skriva i, eller
  att prova Skapa bokmärken i planhandling med.
- **Innehåll utan geometri** (till exempel bostadsförsörjning som bara beskrivs i text), skapas från Skapa bokmärken i planhandling och
  sparas i gruppens ytlager med tom geometri. Mark- och vattenanvändning måste ha geometri enligt föreskrifterna.
- **Gruppen avgör symbolen, värdet avgör färgen.** Varje grupp (innehållstyp i Boverkets modell, till exempel
  Klimatrelaterade risker) har en egen kantlinje, som också används för linjer, och en egen punktform: riksintressen
  trianglar, klimatrisker nedåtvända trianglar, miljökvalitetsnormer romber och så vidare. Värdena i ÖP-katalogen har
  gruppens symbol i en egen färg (Utvecklingsinriktning klassas på den kompletterande utvecklingsinriktningen).
  Mark- och vattenanvändning har heltäckande färger lånade från detaljplanens användningsområden (Bostadsbebyggelse
  gul som B, Verksamheter beige som Z, Vatten blå som W osv.); där detaljplanens färger ligger för nära varandra (T och
  GATA, E och W, C och Z) har värdet fått en egen färg i samma familj, och alla par skiljer sig med ΔE00 minst 8,5
  (CIEDE2000). Övrigt innehåll ritas som överlägg med gruppens kant och svag genomskinlig fyllning, så att
  markanvändningen syns under. Riksintressen enligt miljöbalken (underlag) ritas utan fyllning och med ihåliga
  punkter. Objekt utan innehållstyp ritas i orange. Symbolerna är pluginets eget förslag; Boverket styr inte hur en
  översiktsplan visas. Se `docs/symbologi.md`.
- **Symbolerna fungerar i webbkartor:** bara QGIS enkla symboler (enfärgade ytor, genomskinlighet, linjer med egna
  strecklängder och punktformerna cirkel, kvadrat, triangel, stjärna och kors, vridna för romb, nedåtvänd triangel och
  x). Inga mönster, skrafferingar, bilder eller typsnittssymboler. Lagren klassas direkt på fältet, så att SLD-filtren
  blir vanliga jämförelser. Stilen exporteras som SLD för GeoServer med bara standarddelar; det kontrolleras i
  testerna.
- **Nytt: planer i en PostGIS-databas, med utcheckning och incheckning (som i Rita Detaljplan).** *Ny
  översiktsplan* kan lägga planen i ett schema i en databas (en av QGIS sparade PostgreSQL-anslutningar); schemat
  delas av flera planer med en kolumn `plan` i varje tabell. *Öppna översiktsplan* visar en meny med fil eller databas,
  som i Rita Detaljplan. En
  plan i databasen är skrivskyddad; *Checka ut* låser den och gör en lokal GeoPackage att redigera, *Checka in*
  skriver tillbaka planen i en transaktion och släpper låset, och utcheckningen kan också kastas. Låst av någon
  annan: man ser vem och sedan när och kan bryta låset. En avbruten utcheckning kan tas upp igen. Tabellnamn som är för långa för
  PostgreSQL (Särskilt värdefull kulturmiljö) kortas i databasen, och ett schema som pluginet själv började skapa tas bort
  igen om det går fel. Inte färdigprovat mot en riktig databas.
- **Knappar som inte går att använda är gråa:** utan öppen plan går bara *Ny* och *Öppna*, och *Rita yta/linje/punkt*,
  *Importera geometri*, *Tilldela innehåll* och *Kopiera innehåll* kräver att redigeringen är påbörjad med pennan.
- **Nytt: verktyg som i Rita Detaljplan.** *Börja redigera* (pennan) öppnar alla planens lager för redigering och
  *Avsluta redigering* (disketten, som i Rita Detaljplan) frågar: spara och avsluta, förkasta och avsluta, eller
  avbryt. Den tidigare separata *Spara*-knappen är borttagen ur verktygsfältet (*Spara alla redigeringar* finns kvar
  i menyn). *Markera* markerar planens innehåll med klick eller rektangel
  (Ctrl/Skift lägger till, högerklick avmarkerar) och gör objektets lager aktivt; *Avmarkera alla*. *Kopiera
  innehåll* ger andra objekt samma grupp, innehållstyp, kompletterande innehållstyp, sambandsnivå, precisering och
  utbyggnadsordning som objektet man klickade på först (inte namnet); otilldelad geometri får innehållet och annat
  innehåll byter typ med bibehållen identitet.
- **Nytt: Exportera** kontrollerar planen och sparar den i Lantmäteriets format *Översiktsplan 2.0* (JSON, mediatyp
  `application/vnd.lm.oversiktsplan.v2+json`): planen, beslutet och allt innehåll med värden ur ÖP-katalogen (med
  katalogens id:n), geometri enligt Lantmäteriets geometri 2.0.1 (planens koordinatsystem, ytterringar moturs) och kopplingarna
  till planhandlingens bokmärken. Kontrollen listar fel och varningar; dubbelklick visar objektet. Inte validerad mot
  schemat eller provad i NGP.
- **Nytt: Importera geometri** (knapp i verktygsfältet och i menyn): kopierar ytor, linjer och punkter från ett lager
  i QGIS, eller en datakälla som läggs till med QGIS datakällshanterare, till lagren under *Att tilldela*, utan
  attribut. Valfritt bara markerade objekt. Geometrin omvandlas till planens koordinatsystem, kurvor görs om till raka linjer,
  höjd- och M-värden tas bort och geometrisamlingar delas upp efter slag. Objekten läggs i redigeringsbufferten (Spara
  eller Ångra) och tilldelas sedan innehåll som det man ritat.
- **Nytt: Öppna översiktsplan** lägger till en plan som skapats tidigare.
- **Nytt: verktygsfältet Rita Översiktsplan** med *Ny översiktsplan*, *Öppna översiktsplan*, *Rita yta*, *Rita
  linje*, *Rita punkt*, *Importera geometri*, *Tilldela innehåll*, *Planens uppgifter* (fler knappar ovan). Med flera planer öppna gäller
  kommandona planen som det markerade lagret hör till. Verktygsfältet kan visas och döljas i menyn.
- **Pluginets egna tabeller** i planen: `rita_otilldelad_yta`, `_linje` och `_punkt` för ritad geometri utan innehåll,
  och standardvärdena i metadatatabellen. En plan från en tidigare utvecklingsversion (schema 1 eller 2) får dem, och
  tabellen för beslut, när den öppnas.
- **Medvetna avvikelser från Boverkets mall** (beskrivna i `docs/datamodell.md`): alla lager i samma koordinatsystem med `fid`
  och `geom`, kommunnamn i planens tabell, riktiga datum- och ja/nej-fält, och mallens restkolumner borttagna.
- **Eget märke: Ö.** R:et står för hela Rita-sviten, och varje plugin får en egen bokstav i samma stil: en linje med
  brytpunkter och ett streckat gummiband. Översiktsplanens Ö har ett streckat gummiband men inget hårkors, eftersom
  gränserna i en översiktsplan är illustrativa och inte exakta. Bannrar och social preview byggs med
  `tools/build_branding.py`. Svitens tre märken (R, D och Ö) finns i `docs/images/marken/`.
- Byggskript, releasetest, kommunlista (SCB) och Om-dialog är hämtade från Rita Detaljplan.
