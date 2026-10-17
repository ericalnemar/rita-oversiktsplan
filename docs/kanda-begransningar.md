# Kända begränsningar – Rita Översiktsplan

Pluginet är under utveckling. Här står vad som saknas och vad som inte är provat. Rapportera gärna vad du upptäcker
under [Issues](https://github.com/ericalnemar/rita-oversiktsplan/issues).

## Vad som saknas

- **Kartbilden är inte färdig.** Arbete pågår med hur planen visas i kartan: symbologin (färger, kantlinjer och punktsymboler per innehållstyp) och presentationen i övrigt kommer att ändras. Se [Symbologi](symbologi.md).
- **Kontroll mot specifikationen.** Exporten kontrollerar att det som Lantmäteriets format kräver finns, men inte
  Lantmäteriets valideringsregler i NGP (de är inte genomgångna än).
- **Leverans** till Nationella geodataplattformen (NGP). Exporten till Lantmäteriets JSON-format finns, men är inte
  validerad mot Lantmäteriets schema eller provad i NGP, och specifikationen är i testversion.
- **Tolkningar i exporten:** hur dokumentens externa referens ska fyllas i (identitet, producentens identitet,
  tidsstämpel, vad den avser) säger schemat inte, se `core/export_lm.py`. Länkar till dokument tas bara med om de är
  webbadresser. *Berör annat innehåll* och externa referenser till riksintressen följer inte med.
- **Arkivpaket.**
- **Kopplingar som du själv måste sköta:** underlag, *berör annat innehåll* och externa referenser till riksintressen
  fylls inte i av pluginet. Tabellerna finns, men det finns inga verktyg för dem än.
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
  testschema. Alla planer i ett schema delar tabeller och koordinatsystem. Planer i databasen kan inte
  uppgraderas från äldre schemaversioner (stödet är nytt i den här versionen). Skapa bokmärken i planhandling sparar inte kopplingar i en
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
