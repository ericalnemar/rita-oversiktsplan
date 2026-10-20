# Kända begränsningar – Rita Översiktsplan

Pluginet är under utveckling. Här står vad som saknas och vad som inte är provat. Rapportera gärna vad du upptäcker
under [Issues](https://github.com/ericalnemar/rita-oversiktsplan/issues).

## Vad som saknas

- **Hämtade ytor och linjer förenklas** (5 m tolerans, hål under 1 000 m² tas bort), så de följer inte myndighetens geometri exakt. Gränserna i en översiktsplan är illustrativa, men använd myndighetens egen tjänst när exakta gränser behövs.
- **Etiketten med riksintressets slag** är ett uttryck (namn – värde); i GeoServer blir det en funktion i SLD, som inte är provad.
- **Markanvändning från Topografi 10** är bara provad med låtsade filer med samma skikt och fält som Lantmäteriets (och en med 60 000 ytor för tiden: under 10 sekunder), inte med en riktig nedladdning: den kräver inloggning på Geotorget. Objekttyper och ändamål är tagna ur Lantmäteriets dokumentation av Topografi 10 (2026-10-20); skikten hittas på fältet `objekttyp`. Omklassningen är pluginets förslag, och Topografi 10 visar vad som finns på marken, inte alltid användningen. Sankmark, byggnader, mindre vägar och stigar tas inte med i förslaget. Ytor och linjer förenklas med 5 m.
- **Topografi 10:s färger:** några av dem är mycket ljusa (öppen mark, industrigrå) och syns svagt mot vit bakgrund, som i Lantmäteriets egen karta. Grönområde har en egen blågrön ton, eftersom Topografi 10 saknar park och idrottsplanernas gröna låg för nära skogen; vägtrafik fick en mörkare grå av samma skäl.
- **Utbyggnadsordningen** syns bara i mark- och vattenanvändningens ytor (inte linjer, punkter eller
  utvecklingsinriktning). Med fler än fem–sex etapper blir tonerna svåra att skilja åt. Etappens text i fältet är
  pluginets format, `namn (period)`; Lantmäteriets format har bara fritext.
- **Bården på överläggens ytor i GeoServer är inte provad.** Den är en kantlinje med förskjutning (`PerpendicularOffset` i SLD); i QGIS hamnar den alltid innanför kanten, men GeoServer kan förskjuta den utåt beroende på åt vilket håll ytans kant är ritad.
- **Nya symboler når inte sparade projekt.** Symbolerna sätts när planen läggs till i kartan. Ett projekt som sparats med en äldre version behåller de gamla; öppna planen i ett nytt projekt för att få de nya.
- **Pilspetsarna i GeoServer är inte provade.** Stilfilerna från *Spara stilar för GeoServer (SLD)…* använder GeoServers funktioner `endPoint`/`endAngle`; vridningen är beräknad, inte provad. Etiketternas placering i GeoServer kan skilja sig från QGIS.
- **Kartbilden är inte färdig.** Arbete pågår med hur planen visas i kartan: symbologin (färger, kantlinjer och punktsymboler per innehållstyp) och presentationen i övrigt kommer att ändras. Se [Symbologi](symbologi.md).
- **Kontroll mot specifikationen.** Exporten kontrollerar Lantmäteriets regler (OP-JSON-… och ÖP-X…) så som pluginet
  tolkar dem ur objekttypskatalogen och dataproduktspecifikationen (test 4). Den är inte provad mot Lantmäteriets
  validering i NGP, och den validerar inte mot JSON-schemat (ÖP-X01).
- **Ändring av översiktsplanen** är pluginets tolkning av hur en ändring ska se ut i Lantmäteriets format: ändringen
  är ett eget beslut som påverkar innehållet i ändringen, och innehållet har ändringens datum påbörjat och
  planhändelse. Ett beslut utan datum räknas som en pågående ändring och exporteras inte. Bara en ändring kan pågå åt
  gången. Planen som helhet behåller sin planhändelse.
- **Hämta riksintressen** använder Boverkets karttjänst (februari 2026). Lagernumren i tjänsten är inskrivna i
  pluginet: byter Boverket tjänst eller lager slutar hämtningen fungera tills pluginet uppdateras. Fältet med
  myndighetens id skiljer sig mellan lagren; där inget id finns (till exempel turism och rörligt friluftsliv)
  känns objekten igen på värde och geometri vid en ny hämtning. Påverkansområden, buller- och hinderytor hämtas inte.
  Hämtningen är provad mot Boverkets riktiga tjänst för ett område kring Lidköping, men inte i en riktig QGIS.
- **Kommunens yta** i Ny översiktsplan hämtas från Lantmäteriets kommunytor via länsstyrelsernas nationella visningstjänst (lager och fält inskrivna i pluginet). Byter länsstyrelserna tjänst slutar det fungera tills pluginet uppdateras; då ritar man plangeometrin själv. Provat mot tjänsten för Lidköping, Munkfors och Stockholm, inte i en riktig QGIS.
- **Kommunens ställningstagande** kopplas till sitt riksintresse med *berör annat innehåll*. Det är pluginets
  tolkning: Lantmäteriets specifikation säger inte hur ett ställningstagande ska peka på riksintresset.
- **Leverans till NGP är inte provad mot Lantmäteriet.** Klienten är kopierad från Rita Detaljplan och testad mot en
  låtsasserver som beter sig som Uppdatering-API:et. Att informationstypen heter `oversiktsplan` och att
  mediatypen `application/vnd.lm.oversiktsplan.v2+json` tas emot är antaganden utifrån Lantmäteriets
  specifikationssida. Exporten är inte validerad mot Lantmäteriets schema, och specifikationen är i testversion.
  Prova i verifieringsmiljön först.
- **Tolkningar i exporten:** hur dokumentens externa referens ska fyllas i (identitet, producentens identitet,
  tidsstämpel, vad den avser) säger schemat inte, se `core/export_lm.py`. Länkar till dokument tas bara med om de är
  webbadresser. Riksintressets id blir en extern referens med samma värde som identitet och producentens
  identitet, och tidsstämpeln är *hämtat datum* (eller innehållets versionsdatum): det är tolkningar.
- **Arkivpaketet** följer Boverkets mallar, som avviker från PREMIS egen schemafil; paketet är inte validerat mot
  schemat. Planens uppgifter ligger i en `objectCharacteristicsExtension` (Boverket anger inte hur). Datum skrivs som i
  mallarna. Pluginet gör inga filer till PDF/A och kontrollerar dem inte. Paketet sparas som en mapp, inte i ett
  e-arkiv.
- **Planhandlingen** delas in i avsnitt efter rubrikformaten. Text utan rubrik ovanför och delar av ett avsnitt kan inte
  få egna bokmärken, och flera avsnitt kan inte slås ihop till ett bokmärke. Ett dokument åt gången är öppet i Skapa
  bokmärken i planhandling (flera går, men de hålls isär efter filnamn). Det finns ingen granskningskopia med kommentarer, som i
  Rita Detaljplan. Byter du namn på eller flyttar kopian med bokmärken hittas kopplingarna efter filnamnet.
- **Kartan i Skapa bokmärken i planhandling** är en förenklad bild (inga bakgrundskartor, inga etiketter). Stora planer med många
  brytpunkter är inte provade och kan bli tröga att rita. Det du granskat (Godkänn) sparas först när du sparar.
- **Importera geometri** tar bara med geometrin: attribut som namn eller användning i källan följer inte med och
  måste anges med Tilldela innehåll. Ogiltiga geometrier lagas inte. Stora källor är inte provade.
- **Webbversionen** tar inte med bilder (bara deras alternativtext), fotnoter, kommentarer, sidhuvud och sidfot eller
  Words formatering (typsnitt, färger, indrag). Sammanslagna tabellceller visas som vanliga celler. Hur själva texten
  ska lämnas till Nationella geodataplattformen är inte utrett; webbversionen är tänkt för kommunens egen webb.
- **Varningen för mark- och vattenanvändning utan text** är pluginets egen kontroll, inte ett krav ordagrant ur
  föreskrifterna.
- **Innehåll utan geometri** syns inte i kartan; ändra eller ta bort det i gruppens attributtabell.
- **PostGIS.** Att skapa och öppna planer i en databas och att checka ut och checka in är bara testat mot en
  låtsasdatabas. SQL:en har inte körts mot en riktig PostgreSQL med PostGIS: prova först på en testplan i ett
  testschema. Alla planer i ett schema delar tabeller och koordinatsystem. Ett schema från 0.1.0–0.1.2
  (schema 3) uppgraderas när en plan i det öppnas första gången, vilket kräver rätt att ändra tabellerna; äldre
  scheman än så kan inte uppgraderas. Skapa bokmärken i planhandling sparar inte kopplingar i en
  plan som inte är utcheckad.
- **Samma yta med flera innehåll.** En ritad yta får ett innehåll när den tilldelas. Ska samma område ha flera
  innehåll (till exempel markanvändning och ett riksintresse) ritar du ytan en gång till, eller kopierar den.
- **Snappning och topologi.** Pluginet ställer inte in snappning åt dig; använd QGIS egna inställningar.
- **Uppgradering av katalogen i en befintlig plan.** En plan behåller den ÖP-katalog den skapades med.

## Underlagen ändras fortfarande

- **Lantmäteriets nationella specifikation för översiktsplan** har status *test* (test 4) under 2026 och är inte
  fastställd.
- **Boverkets GIS-databasmodell** (version 0.3), som pluginets tabeller följer, uppdateras under teståret
  allteftersom specifikationen testas. Pluginet avviker medvetet från mallen på några punkter, se
  [Datamodell](datamodell.md).
- **ÖP-katalogen** får nya versioner upp till två gånger per år. Pluginet har version 2.2 (juni 2026).

## Inte provat

- Hela pluginet har bara körts i automatiska tester, **inte i en riktig QGIS med en riktig plan**.
- Testat med QGIS 4.2.2 på Windows. Andra versioner och Linux/macOS är inte provade.
- Filen är inte provad i ArcGIS eller i Boverkets egna verktyg.
