# Användarhandledning – Rita Översiktsplan

Pluginet är i ett tidigt skede: du kan skapa en översiktsplan, rita dess innehåll, ställa in planens uppgifter och
öppna planen igen. Kontroll, leverans och arkivering kommer senare. Se [Kända begränsningar](kanda-begransningar.md)
för vad som saknas.

Arbetsgången är densamma som i Rita Detaljplan: **rita först, tilldela sedan.** Du ritar en yta, linje eller punkt, och
ger den sedan innehåll med verktyget *Tilldela innehåll*. Det som gäller hela planen, till exempel planhändelsen,
ställer du in en gång under *Planens uppgifter*.

## Verktygsfältet och menyn

Verktygsfältet **Rita Översiktsplan**, från vänster:

| Knapp | Gör |
|---|---|
| Karta med grönt plus | **Ny översiktsplan…** (se nedan) |
| Mapp | **Öppna översiktsplan…**: lägger till en plan som du skapat tidigare i kartan, från en fil eller en databas |
| Databas med pil ned/upp | **Checka ut / Checka in**: för en plan i en PostGIS-databas (se nedan) |
| Penna | **Börja redigera**: öppnar alla planens lager för redigering |
| Diskett | **Avsluta redigering**: frågar om ändringarna ska sparas eller kastas och avslutar redigeringen |
| Skrivplatta | **Planens uppgifter**: planen, planhändelsen, beslutet och standardvärden för nytt innehåll |
| Låda med pil upp | **Leverans och export**: kontrollerar planen, sparar den i Lantmäteriets format, levererar den till NGP eller skapar ett arkivpaket (se nedan) |
| Dokument med grön etikett | **Skapa bokmärken i planhandling**: öppnar programmet som kopplar textavsnitten i Word till planens innehåll (se nedan) |
| Yta med muspekare | **Markera**: klicka eller dra en rektangel för att markera planens innehåll |
| Streckad yta med rött kryss | **Avmarkera alla** |
| Orange streckad yta | **Rita yta** |
| Orange streckad linje | **Rita linje** |
| Orange punkt | **Rita punkt** |
| Röd låda med pil ned | **Importera geometri**: hämta ytor, linjer och punkter från ett annat lager (se nedan) |
| Lapp med muspekare | **Tilldela innehåll**: klicka på det du ritat och välj vad det är |
| Två lappar med grönt plus | **Kopiera innehåll**: ge andra objekt samma innehåll som ett objekt du klickar på (se nedan) |
| Två ytor med blå streckad linje | **Berör annat innehåll**: koppla ett innehåll till det innehåll det berör (se nedan) |

Knapparna är desamma, och står i samma ordning, som i Rita Detaljplan.

Knappar som inte går att använda just nu är **gråa**: utan en öppen plan går bara *Ny* och *Öppna*, och för att rita,
importera, tilldela, kopiera eller koppla innehåll måste redigeringen vara påbörjad med **pennan** (*Börja redigera*). En
plan i en databas checkas ut när du klickar på pennan.

Har du flera planer öppna gäller knapparna den plan som det markerade lagret hör till, annars den översta planen i
lagerpanelen.

Samma kommandon finns under **Insticksprogram → Rita Översiktsplan**. Där kan du också visa eller dölja
verktygsfältet, och öppna **Om Rita Översiktsplan…** med version, licens, en länk till den här handledningen och till webbsidan [ritaplan.xyz](https://ritaplan.xyz).

## Skapa en ny översiktsplan

1. Klicka **Ny översiktsplan…**
2. Fyll i:
   - **Kommun.** Skriv några bokstäver och välj i listan. Kommunkoden följer med.
   - **Planens titel**, till exempel *Översiktsplan 2040*.
   - **Lagras i**: **lokal fil** (GeoPackage) eller **PostGIS-databas**. Databasen går bara att välja om QGIS har
     sparade PostgreSQL-anslutningar.
   - För en fil: **Filnamn** (föreslås utifrån titeln) och **Spara i mapp**.
   - För en databas: **Anslutning** (en av QGIS sparade PostgreSQL-anslutningar), **Schema** (delas av flera
     planer: finns det redan läggs planen till där, annars skapas det) och **Plan-id** (föreslås utifrån titeln;
     gemener a–z, siffror och understreck).
   - **Påbörjad**: dagen arbetet med planen påbörjades.
   - **Koordinatsystem**: SWEREF 99 TM (förvalt) eller en av de tolv lokala SWEREF 99-zonerna. Lantmäteriets
     specifikation tillåter alla tretton; Boverkets GIS-databasmodell använder SWEREF 99 TM. Det går inte att
     ändra efteråt, och i en databas delar alla planer i samma schema koordinatsystem.
3. Klicka **Skapa**.

Pluginet skapar en GeoPackage-fil (en databas i en enda fil) med samma tabeller som Boverkets GIS-databasmodell för
ÖP-modellen, och lägger till planen överst i lagerpanelen i gruppen **Översiktsplan – *titeln***.

## Planens uppgifter

Klicka **Planens uppgifter**. Dialogen har fem flikar:

- **Planen**: titel, datum då planen påbörjades, och om planen tagits fram digitalt eller är en äldre plan som
  digitaliseras (då med en beskrivning av hur).
- **Planhändelse**: det senaste som hänt planen, till exempel *Samrådsunderlag färdigställt* eller *Antagen*, och
  datumet. Nytt innehåll får planens planhändelse. Med **Ge allt innehåll i planen samma planhändelse** (ikryssad
  från början) får även det innehåll som redan finns den nya planhändelsen.
- **Beslut**: antagandebeslutets **diarienummer** och datum då planen antogs, överklagades och **fick laga kraft**.
  Boverkets föreskrifter (BFS 2024:2, 2 kap. 2 §) kräver diarienumret och datumet för laga kraft. Beslutande är alltid
  kommunfullmäktige i planens kommun. Beslutet sparas i tabellen *Beslut* och planen pekar på det.
- **Underlag**: de dokument planen bygger på, ett per rad, med **underlagstyp** ur ÖP-katalogen (till exempel
  *Planeringsunderlag* eller *Miljökonsekvensbeskrivning*), dokumentets namn, en **länk** (webbadress) eller fil, och
  datum. *Lägg till fil…* fyller i namn och sökväg. Lantmäteriets format kräver minst ett underlag. Dokument med samma
  underlagstyp samlas under samma underlag i exporten, och bara webbadresser följer med som länkar. Underlagen sparas i
  tabellerna *Underlag*, *Underlagets dokument* och *Dokumentreferenser*.
- **Standardvärden för innehåll**: vertikal avgränsning, om innehållet är under ersättning, datum påbörjat och
  presentationsskala. Värdena sätts på varje objekt som tilldelas innehåll från och med nu.

Klicka **Spara**. Uppgifterna sparas direkt. Fyll gärna i planhändelsen innan du börjar tilldela innehåll.

## Rita och tilldela innehåll

1. Klicka **Rita yta**, **Rita linje** eller **Rita punkt** och rita som vanligt i QGIS. Inget formulär visas: det du
   ritar hamnar i gruppen **Att tilldela** överst i planen och syns i orange.
2. Klicka **Tilldela innehåll** och sedan på det du ritat. En dialog öppnas:
   - **Grupp**, till exempel *Mark- och vattenanvändning* eller *Klimatrelaterade risker*. Bara grupper som kan ha
     den geometrin visas (Plangeometri och Område är bara ytor).
   - **Innehållstyp** ur ÖP-katalogen, med katalogens beskrivning under.
   - Det som gäller just det här objektet: **Namn** och **Precisering**, och för vissa grupper **Kompletterande**
     innehållstyp, **Sambandsnivå** och **Utbyggnadsordning**.
3. Klicka **Tilldela**. Objektet flyttas till rätt lager och ritas med gruppens symbol.
4. Klicka **Avsluta redigering** (disketten) och välj **Spara och avsluta** när du är klar.

### Importera geometri i stället för att rita

Finns geometrin redan, till exempel i den gällande översiktsplanen, en utredning eller en DWG/DXF-fil, kan du hämta
den i stället för att rita om den:

1. Klicka **Importera geometri** (den röda lådan med pil ned).
2. Välj ett **lager** som redan finns i QGIS, eller klicka **Lägg till datakälla…**. Då öppnas QGIS vanliga
   datakällshanterare (filer som GeoPackage, Shape och DXF, databaser och webbtjänster som WFS), och lagret du
   lägger till väljs direkt i dialogen.
3. Kryssa i **Bara markerade objekt** om du bara vill ha det du markerat i lagret.
4. Klicka **Importera**.

Bara **geometrin** följer med, inga attribut. Ytor hamnar i *Otilldelad yta*, linjer i *Otilldelad linje* och
punkter i *Otilldelad punkt* under **Att tilldela**, och ges sedan innehåll med *Tilldela innehåll* precis som det du
ritat. Pluginet omvandlar geometrin till planens koordinatsystem, gör om kurvor till raka linjer och tar bort höjdvärden. En
multipunkt blir en punkt per del. Källan ändras inte. Det importerade ligger i redigeringsbufferten: spara med **Avsluta redigering**
när du är nöjd, eller ångra med QGIS Ångra. Ogiltiga geometrier (till exempel ytor som korsar sig själva) importeras,
men pluginet säger hur många de är.

*Tilldela innehåll* är aktivt tills du väljer ett annat verktyg, så att du kan tilldela flera objekt i rad.

Klickar du på något som **redan har innehåll** öppnas samma dialog, och du kan byta grupp eller innehållstyp. Objektet
behåller sin identitet och sina övriga uppgifter. Ligger flera objekt på varandra väljer du i en meny vilket du menar.
Otilldelad geometri väljs alltid före innehåll under den.

Det här sätts automatiskt på varje objekt som tilldelas innehåll:

- **Objektidentitet**: ett unikt id (UUID).
- **Versionen gäller från**: tidpunkten då objektet fick innehåll.
- **Illustrativa gränser**: alltid *ja*, som specifikationen kräver.
- **Planhändelse** och dess datum: planens.
- **Vertikal avgränsning**, **under ersättning**, **datum påbörjat** och **presentationsskala**: standardvärdena
  under Planens uppgifter.

Ett enskilt objekt kan ändras i attributformuläret (identifieringsverktyget eller attributtabellen i QGIS).

### Markera, kopiera och redigera

**Markera** markerar planens innehåll och det som ska tilldelas, oavsett vilket lager som är valt i lagerpanelen.
Klicka på ett objekt (ligger flera på varandra väljer du i en meny) eller dra en rektangel. Ctrl- eller Skift-klick
lägger till i markeringen, och högerklick avmarkerar allt. Objektets lager blir aktivt, så att QGIS egna verktyg
(flytta, dela, brytpunkter) fungerar direkt på det. **Avmarkera alla** tar bort markeringen i planens lager.

**Kopiera innehåll** fungerar som *Kopiera bestämmelser* i Rita Detaljplan: klicka först på ett objekt med innehåll
(det visas i grönt) och sedan på de objekt som ska få samma innehåll. Det som kopieras är grupp, innehållstyp,
kompletterande innehållstyp, sambandsnivå, precisering och utbyggnadsordning, inte namnet. Målet kan vara otilldelad
geometri (som då får innehållet) eller annat innehåll (som byter typ men behåller sin identitet). Verktyget ligger
kvar, så att du kan klicka på flera objekt i rad. Högerklick eller Esc väljer ett nytt objekt att kopiera från.

**Berör annat innehåll** kopplar ihop innehåll som hänger ihop, till exempel en klimatrisk som berör ett område för
bostadsbebyggelse (`berorAnnatInnehall` i Lantmäteriets format). Klicka först på innehållet du utgår från (det visas i
grönt, och det som det redan berör i blått) och sedan på det innehåll det berör. Klicka på samma innehåll igen för att
ta bort kopplingen. Verktyget ligger kvar; högerklick eller Esc väljer ett nytt innehåll att utgå från. Kopplingen går
åt ett håll: att klimatrisken berör bostadsområdet säger inget om bostadsområdet. Otilldelad geometri kan inte kopplas.
Kopplingarna sparas när du sparar redigeringen.

**Riksintressets id.** För riksintressen (kommunens ställningstagande och riksintressen enligt 3 och 4 kap. MB) har
*Tilldela innehåll* ett fält för riksintressets id hos den myndighet som pekat ut det. Det blir en extern referens i
exporten.

**Pennan** (*Börja redigera*) öppnar alla planens lager för redigering på en gång. *Avsluta redigering* frågar om
ändringarna ska sparas eller förkastas och stänger redigeringen.

## Planhandlingen: koppla texten till innehållet

Översiktsplanens text (planhandlingen) skrivs i Word som vanligt. Med **Skapa bokmärken i planhandling** (dokument med en grön
etikett i verktygsfältet) kopplar du textavsnitten till planens innehåll, så som Boverkets ÖP-modell och Lantmäteriets
specifikation beskriver: varje avsnitt får ett Word-**bokmärke**, och bokmärkets namn sparas tillsammans med innehållet
det gäller. Ett avsnitt kan gälla flera objekt, och ett objekt kan beskrivas i flera avsnitt.

Knappen öppnar ett **eget fönster**, byggt som motsvarande program för planbeskrivningen i Rita Detaljplan, med fyra steg i
toppfältet. Fönstret låser inte QGIS: du kan markera och rita i kartan medan det är öppet. Klickar du på knappen igen
läses planen om (till exempel efter att du ritat mer).

1. **Filer.** Planen är redan vald (den aktiva planen i QGIS). Välj planhandlingen (.docx) eller dra den till
   fönstret. *Öppna senaste* öppnar dokumentet du arbetade med senast i den här planen.
2. **Avsnitt.** Varje **rubrik** (formatmallarna Rubrik 1, 2, 3) blir ett avsnitt som räcker till nästa rubrik. Texten
   visas som ett papper, ett kort per avsnitt. Programmet föreslår en **avsnittstyp** ur ÖP-katalogen utifrån rubriken
   och säger varför under *Varför*: *Ställningstaganden* blir Ställningstagande och underrubrikerna ärver typen, annars
   blir det Beskrivning. Granska varje förslag: byt typ i listan, klicka **Godkänn** (eller Enter), eller **Inget
   bokmärke** för text som inte ska ha bokmärke. Rubriker utan egen text får inget bokmärke från början. J och K bläddrar.
3. **Koppling.** Välj ett avsnitt till vänster. I mitten syns texten och det avsnittet är kopplat till. Koppla genom
   att:
   - **klicka på innehållet i kartan** till höger (klicka igen för att ta bort kopplingen; rullhjulet zoomar, dra för
     att flytta, dubbelklicka för att se allt),
   - **kryssa i listan** under kartan (den visar också hur många avsnitt varje objekt redan är kopplat till),
   - **Hämta markerat i QGIS**: det som är markerat i QGIS karta,
   - **Gäller hela planen**: för till exempel syftet och sammanfattningen,
   - **Nytt innehåll utan geometri…**: för innehåll som bara beskrivs i text, till exempel bostadsförsörjning eller
     planens konsekvenser. Du väljer grupp och innehållstyp som när du tilldelar innehåll, och rubriken föreslås som
     namn. Mark- och vattenanvändning måste ha en geometri enligt föreskrifterna och finns inte med här.

   **Visa i QGIS** markerar avsnittets innehåll i QGIS karta. Krysset på en koppling tar bort den.
4. **Kontroll och spara.** Kontrollen visar fel (koppling till något som inte finns i planen längre), varningar
   (avsnitt som inte är granskade, mark- och vattenanvändning som inte är kopplad till något avsnitt) och information.
   *Gå till* visar var. Till höger syns raderna som sparas i planen. Klicka **Spara…** vid *Kopia med bokmärken
   och kopplingar*: programmet sparar en kopia av dokumentet med bokmärkena, som standard *namn*_bokmarken.docx bredvid
   originalet, och kopplingarna direkt i planens dokumenttabeller. **Originalet ändras aldrig.** Med rutan *Spara
   också en webbversion* ikryssad (standard) sparas dessutom en **webbsida** (*namn*_bokmarken.html) bredvid kopian:
   texten med rubriker, listor, tabeller och länkar, där varje avsnitt har sitt bokmärke som adress
   (*namn*_bokmarken.html#op_3f2a…). Dokumentets titel blir sidans huvudrubrik (`<h1>`), Rubrik 1 blir `<h2>` och så
   vidare. Bilder visas som sin alternativtext. *Översikt över kopplingarna* sparar kopplingarna som en CSV-fil för
   Excel.

**Arbetsgången genom skedena:** skapa bokmärken första gången när samrådsunderlaget är klart. Fortsätt sedan att skriva i den
**kopian med bokmärken**, och öppna den igen inför granskning och antagande: avsnitten behåller sina bokmärken, så bara nya
rubriker och ändrat innehåll behöver ses över, och webbversionen görs om när du sparar. Öppnar du originalet (utan
bokmärken) i en plan som redan har bokmärken varnar programmet och erbjuder att öppna kopian med bokmärken i stället.

**En webbkarta** kan länka från planens innehåll till texten: raderna i `dokumentavsnitt` säger vilket bokmärke som
hör till vilket objekt (`objektidentitet`), och bokmärket är adressen till avsnittet i webbversionen.

Fortsätt sedan att skriva i den **kopian med bokmärken**. Öppnar du den igen känns bokmärkena igen, och avsnittstyperna och
kopplingarna visas som granskade. Ett avsnitt behåller sitt bokmärke så länge rubriken finns kvar, och när du sparar
igen skrivs kopian med bokmärken över. Lägger du till rubriker får de nya avsnitten nya bokmärken. Stänger du fönstret
med ändringar som inte är sparade frågar programmet först.

**Utkast att börja från:** [`exempel/Planhandling_mall_ÖP-katalogen_2.2.docx`](../exempel/Planhandling_mall_ÖP-katalogen_2.2.docx) är en planhandling med en
rubrik för allt innehåll i ÖP-katalogen (Rubrik 1–3), katalogens vägledning i grått och plats för kommunens text. Ta
bort de rubriker planen inte behöver. Rubrikerna är valda så att Skapa bokmärken i planhandling föreslår rätt avsnittstyp.

Innehåll utan geometri syns inte i QGIS karta, men finns i gruppens ytlager (i attributtabellen) och i listan i
Skapa bokmärken i planhandling.

## Planens lager

I gruppen **Översiktsplan – *titeln*** finns:

- **Översiktsplan**: tabellen med planens uppgifter (en rad).
- **Att tilldela**: det du ritat men ännu inte gett innehåll, en yta, en linje och en punkt.
- **Plangeometri** och **Område**: ytor.
- En undergrupp per innehållstyp, till exempel **Mark- och vattenanvändning**, med tre lager: **yta**, **linje** och
  **punkt**.
- **Beslut, dokument och underlag**: antagandebeslutet och tabeller för hänvisningar till planhandlingen och
  underlagen.

Planen ligger i det koordinatsystem du valde när den skapades. Är projektet tomt när planen läggs till får kartan samma koordinatsystem; annars rörs
kartans inställningar inte.

Varje grupp har en egen symbol, och färgen visar innehållstypen. Teckenförklaringen syns i lagerpanelen. Symbolerna
är pluginets eget förslag, eftersom Boverket inte styr hur en översiktsplan ska visas, och de fungerar i webbkartor.
Se [Symbologi](symbologi.md), och ändra fritt under lagrets egenskaper.

## Leverans och export

**Leverans och export** (lådan med pil upp) kontrollerar planen och sparar den i Lantmäteriets format för översiktsplan:
*Översiktsplan 2.0* (JSON), det format som används vid leverans till Nationella geodataplattformen (NGP).
Specifikationen är i testversion. Filen innehåller:

- **planen**: kommun, titel, planhändelse, datum, underlag och kopplingar till planhandlingen,
- **beslutet**: diarienummer och datum, om det är ifyllt under Planens uppgifter, och vilket innehåll det gäller,
- **allt innehåll**: innehållstyp och övriga uppgifter, geometrin i planens koordinatsystem och kopplingarna till planhandlingens
  bokmärken.

Värden ur ÖP-katalogen skrivs med katalogens id:n. Otilldelad geometri följer inte med. Ändringar som inte sparats
kommer med.

Dialogen visar först vad kontrollen hittade: **fel** (det som Lantmäteriets format kräver men som saknas, till exempel
planhändelse eller en innehållstyp som inte finns i katalogen) och **varningar**. Dubbelklicka på en anmärkning för att
markera och zooma till objektet. Klicka **Spara som JSON…** för att spara filen. Det går även med fel, men då följer
filen inte formatet.

Formatet kräver att planen har minst ett **underlag**; lägg till det under *Planens uppgifter*, fliken *Underlag*.

### Antagandebeslutet gäller innehållet

När du sparar antagandebeslutet under *Planens uppgifter*, fliken *Beslut*, får allt innehåll som ännu inte hör till
ett beslut beslutets id (fältet *beslut*). Innehåll som redan hör till ett annat beslut, till exempel en senare ändring,
rörs inte. I exporten räknar beslutet upp planen och det innehåll det gäller.

### Leverera till NGP

**Leverera till NGP…** skickar planen till Nationella geodataplattformen via Lantmäteriets Uppdatering-API, på samma
sätt som i Rita Detaljplan. Först krävs inställningar: klicka **Inställningar…** (eller *Insticksprogram → Rita
Översiktsplan → Inställningar för leverans till NGP…*) och välj miljö (Lantmäteriets **verifieringsmiljö**, som man
provar i, eller **produktion**) och en autentiseringskonfiguration i QGIS med nyckeln och hemligheten från
Lantmäteriets API-portal. Kommunen måste ha behörighet som producent för översiktsplan.

Pluginet frågar innan något skickas, och säger vart planen skickas och hur många fel kontrollen hittade. Leveransen
sker i bakgrunden; när Lantmäteriet validerat planen visas resultatet med **valideringsrapporten** (det som inte gick
igenom, med Lantmäteriets egna texter). Får planen valideringsfel rättar du dem och levererar igen: planen skickas då
på samma mottagning hos Lantmäteriet.

### Arkivpaket

**Skapa arkivpaket…** (i dialogen eller i menyn) samlar planen och handlingarna i en mapp med bevarandemetadata enligt
Boverkets specifikation *Långtidsbevarande och arkivering av översiktsplan och detaljplan*:

- `oversiktsplan.xml`: planens uppgifter (titel, kommun, planhändelse, diarienummer, datum),
- `metadata/PREMIS.xml`: varje fil med id, kontrollsumma (SHA-256), storlek, format och program, och vad som hänt
  (paketet skapades, av vem),
- `content/`: filerna.

Välj vad som ska med: planens **GeoPackage** (bara för en plan i en fil; en plan i en databas checkar du ut först, eller
nöjer dig med exportfilen), **exportfilen** i Lantmäteriets format, **planhandlingen** med bokmärken och dess
webbversion, **underlagens filer** (de som finns på datorn) och **egna dokument** som du lägger till, till exempel
planhandlingen som PDF/A. Pluginet gör inga filer till PDF/A: spara själv plankarta och planhandling som PDF/A och
kontrollera dem med en PDF/A-validerare (till exempel veraPDF). Pluginet påpekar bara när en PDF inte säger sig vara
PDF/A. Avsluta redigeringen först, så att det du ritat är sparat.

**Kontrollera arkivpaket…** i menyn räknar om kontrollsummorna och säger om någon fil ändrats, saknas eller tillkommit.

## Spara

**Avsluta redigering** (disketten, som i Rita Detaljplan) frågar vad som ska hända med ändringarna i planens lager:
**Spara och avsluta**, **Förkasta och avsluta** eller **Avbryt**. Vill du spara mitt i arbetet utan att avsluta finns
**Spara alla redigeringar** i menyn **Insticksprogram → Rita Översiktsplan** (det sparar alla lager i projektet och
redigeringen fortsätter), och QGIS egen knapp *Spara lagerändringar* fungerar också.

## Planer i en PostGIS-databas: checka ut och checka in

En plan kan ligga i en **PostGIS-databas** i stället för i en fil, så att flera kan arbeta mot samma planer (som i
Rita Detaljplan). Databasen måste ha PostGIS, och anslutningen läggs upp i QGIS som vanligt (Datakällshanteraren →
PostgreSQL); inloggningen sköts av QGIS. Alla planer i samma schema ligger i samma tabeller, och en dold kolumn
`plan` skiljer dem åt.

- **Öppna översiktsplan…** visar en liten meny: *Lokal fil (GeoPackage)…* eller *PostGIS-databas…* (bara om QGIS har
  databasanslutningar). Väljer du databas väljer du anslutning,
  schema och plan.
- En plan som öppnas från databasen är **skrivskyddad**. Att rita direkt mot en databas över nätet blir segt, och två
  som ritar samtidigt skulle skriva över varandra.
- **Checka ut** (databasen med grön pil ned) låser planen i databasen och kopierar den till en lokal GeoPackage som du
  redigerar i full fart. Börjar du rita, importera eller tilldela innehåll i en skrivskyddad plan frågar pluginet om
  den ska checkas ut.
- **Checka in** (samma knapp, nu med orange pil upp) skriver tillbaka hela planen i en enda transaktion, släpper
  låset, pekar lagren mot databasen igen och tar bort den lokala kopian. Avsluta redigeringen först. Här kan du också
  **kasta utcheckningen**: låset släpps utan att något sparas.
- Bara en kan ha planen utcheckad åt gången. Den som försöker checka ut en låst plan ser vem som har den och sedan
  när, och kan **bryta låset** om utcheckningen är övergiven (den andras ändringar som inte checkats in går då inte
  längre att lämna in).
- Kraschar QGIS mitt i arbetet finns kopian kvar i QGIS profilmapp (`rita_oversiktsplan/checkouts`) och erbjuds när du
  checkar ut planen igen.

Spara gärna QGIS-projektet: det kommer ihåg var planen ligger och om den är utcheckad.

## Öppna en plan igen

Välj **Öppna översiktsplan…** och peka ut GeoPackage-filen (eller välj planen i databasen). Sparar du QGIS-projektet följer planens lager med där,
och då behöver du inte öppna planen på nytt. En plan som skapats med en tidigare version av pluginet får de nya
tabellerna (*Att tilldela* och standardvärdena) när den öppnas.
