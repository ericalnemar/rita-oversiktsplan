# Säkerhet

Pluginet hanterar översiktsplaner som filer på din dator, eller i er egen PostGIS-databas. Det enda det kontaktar över
nätverket är den databas du själv valt bland QGIS sparade anslutningar; inloggningen sköts av QGIS, och pluginet sparar
inga lösenord. Inget skickas till Lantmäteriet, Boverket eller någon annan: exporten sparas som en fil, och leverans
till Nationella geodataplattformen finns inte i den här versionen.

Så hanterar pluginet det som kan vara känsligt:

- **Databasen:** värden i SQL skrivs med citering, och schemanamn och planers id får bara innehålla a–z, siffror och
  understreck. Pluginet tar bara bort ett schema som det själv började skapa i samma försök (om det misslyckas), och
  ett annat användares lås bryts bara efter två frågor.
- **Word-dokument:** originalet skrivs aldrig över; bokmärkena läggs i en kopia.
- **Webbversionen (HTML):** all text är kodad, och bara länkar till webbadresser, e-post och avsnitt i samma sida blir
  klickbara (inte till exempel `javascript:` eller filer på datorn).
- **Exporten:** sökvägar till filer på datorn följer inte med, bara webbadresser.

## Rapportera en säkerhetsbrist

Beskriv inte säkerhetsbrister i ett öppet ärende. Använd i stället GitHubs
[privata rapportering](https://github.com/ericalnemar/rita-oversiktsplan/security/advisories/new) (fliken *Security* →
*Report a vulnerability*). Du får svar så snart det går; pluginet underhålls av en enskild person på fritiden.

## Stödda versioner

Bara den senaste utgivna versionen får rättningar.
