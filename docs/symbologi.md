# Symbologi – Rita Översiktsplan

> **Pågående arbete.** Arbete pågår med hur planen visas i kartan: symbologin (färger, kantlinjer och punktsymboler per innehållstyp) och presentationen i övrigt kommer att ändras. Synpunkter tas gärna emot under
> [Issues](https://github.com/ericalnemar/rita-oversiktsplan/issues).

Boverkets föreskrifter om översiktsplan, ÖP-modellen och Lantmäteriets specifikation anger **inte** hur en
översiktsplan ska visas. Det är upp till kommunen. Symbolerna i pluginet är alltså **pluginets eget förslag**, inte
Boverkets. Du kan ändra dem fritt under lagrets egenskaper i QGIS. Symboltabellen finns i koden i
`rita_oversiktsplan/core/styles.py`.

## Gjord för webbkartor

En digital översiktsplan ska kunna visas på webben, till exempel via GeoServer, QGIS Server eller i en webbkarta med
vektortiler. Symbolerna byggs därför bara av QGIS **enkla symboler** (enkel yta, enkel linje, enkel punkt), som
finns i SLD (det stilformat GeoServer läser) och som alla webbkartor kan rita:

- enfärgade ytor och genomskinlighet,
- linjer med egna strecklängder (`stroke-dasharray` i SLD),
- punktformerna **cirkel, kvadrat, triangel, stjärna och kors**, i SLD-standarden (andra former, som femhörning,
  känner GeoServer inte igen). Romb, nedåtvänd triangel och x är samma former vridna, och vridning finns i SLD.
- klassning direkt på fältet, så att SLD-filtren blir vanliga jämförelser som GeoServer förstår.

Det finns **inga mönsterfyllningar, skrafferingar, SVG-bilder eller typsnittssymboler**. Mönster har ett fast avstånd
på skärmen och blir brus när man zoomar ut. De följer ofta inte heller med till webbens format.

Stilen går att exportera som SLD (i QGIS: lagrets egenskaper → Symbologi → Stil → Spara stil → SLD). De automatiska
testerna kontrollerar att exporten bara innehåller standardformer och inga mönster, bilder eller typsnitt. Exporten
är **inte provad i en riktig GeoServer**.

## Gruppen avgör symbolen, värdet avgör färgen

Varje **grupp**, till exempel *Klimatrelaterade risker*, har en egen symbol: en egen kantlinje (strecktyp och
tjocklek), som också används när gruppen ritas som linje, och en egen punktform. Då ser man vilken grupp ett objekt
hör till. **Värdena inom gruppen** har samma symbol och skiljs åt med färgen, till exempel blått för översvämning och
rött för ras. Testerna kontrollerar att ingen grupp har samma kant eller samma punkt som en annan.

| Grupp | Kant och linje | Punkt |
|---|---|---|
| Mark- och vattenanvändning | tunn streckad kant runt heltäckande färg | fylld cirkel |
| Plangeometri | kraftig streck-prick, ingen fyllning | – |
| Område | tät prickad, ingen fyllning | – |
| Utvecklingsinriktning | kraftig streckad | stjärna |
| Riksintresse, kommunens ställningstagande | heldragen | triangel |
| Riksintressen enligt 3 och 4 kap. MB (underlag) | tunn streckad, ingen fyllning | ihålig triangel |
| Miljökvalitetsnormer | tät prickad | romb |
| Övriga förhållanden av väsentlig betydelse | streck-prick-prick | ihålig romb |
| Bostadsförsörjning | streck-prick | kvadrat |
| Mål, planer och program | glesa långa streck | ihålig kvadrat |
| LIS | kraftig gles prickad | x |
| Särskilt värdefull kulturmiljö | dubbelstreck-prick | ihålig cirkel |
| Klimatrelaterade risker | kraftig kort streckad | nedåtvänd triangel |
| Konsekvenser | jämn kort streckad | ihålig nedåtvänd triangel |
| Avvikelse från regionplan | långa streck | ihålig stjärna |
| Mellankommunala och regionala intressen | prick-prick-streck | kors |
| Länsstyrelsens invändningar | kraftig streck-prick-prick | cirkel med vit ring |

Kommunens ställningstagande till ett riksintresse och samma riksintresse enligt miljöbalken har samma färg och samma
punktform (triangel). Underlaget är ihåligt och utan fyllning, ställningstagandet fyllt och med heldragen kant.

Mark- och vattenanvändningen är grunden och skiljs åt med färgen. Färgskillnaden mäts med CIEDE2000 (ΔE00), ett
standardmått på hur olika två färger ser ut för ögat, och testerna kontrollerar att alla par ligger på minst 8,5.

## Mark- och vattenanvändning

Grunden i kartan. Den har heltäckande färg och en tunn, mörkare och streckad kant, eftersom gränserna är
illustrativa. Färgerna utgår från Boverkets färger för detaljplanens användningsområden, med samma färgkoder som i
Rita Detaljplan. Där detaljplanens egna färger ligger för nära varandra, eller detaljplanen saknar motsvarighet, har
värdet fått en egen färg i samma färgfamilj. Till exempel är T (grå) i detaljplanen nästan samma som GATA (ljusgrå),
så *Järnväg* har fått en mörkare grå.

| Innehållstyp | Färg | Detaljplanens färg |
|---|---|---|
| Bostadsbebyggelse | gul | B, oförändrad |
| Funktionsblandad bebyggelse | mörkare brun | (C är brun men för nära Z) |
| Service | röd | S, D, oförändrad |
| Verksamheter | beige | Z, oförändrad |
| Teknisk infrastruktur | gråblå | (E är blågrå men för nära W) |
| Energiproduktion | blåviolett | – |
| Vägtrafik | ljusgrå | GATA, VÄG, oförändrad |
| Järnväg | mörkare grå | (T är grå men för nära GATA) |
| Luftfart | ljuslila | – |
| Sjöfart | marinblå | – |
| Vatten | ljusblå | W, oförändrad |
| Fiske | klarblå | – |
| Vattenbruk | blågrön | – |
| Grönområde | ljusgrön | PARK, oförändrad |
| Natur- och kulturlandskap | mellangrön | (NATUR är samma ljusgröna som PARK) |
| Landsbygd | gråbeige | – |
| Friluftsliv och rekreation | grön | N, oförändrad |
| Jordbruk | sädesgul | (L är samma gröna som N) |
| Skogsbruk | mörkgrön | – |
| Renskötsel | grågrön | – |
| Annan mark- och vattenanvändning | rosa | – |

De två som ligger närmast varandra är *Bostadsbebyggelse* och *Grönområde* (ΔE00 8,9). Där har detaljplanens färger
behållits, eftersom de är grunden i schemat.

Valen är tolkningar. Till exempel kunde *Service* ha fått detaljplanens färg för C (centrum). Säg till om en annan
motsvarighet passar bättre.

Linjer i markanvändningen är streckade i en mörkare ton av färgen. Punkter är cirklar i färgen.

## Övrigt innehåll (överlägg)

Övrigt innehåll ligger ovanpå markanvändningen: gruppens kant i värdets färg, och en svag fyllning (cirka 18 %
täckning). Markanvändningen syns igenom, och innehåll får överlagra varandra enligt Boverket. Några grupper ritas
utan fyllning och med ihåliga punkter: underlaget (riksintressen enligt miljöbalken) och några grupper med ett enda
värde, för att de ska få en egen punktform.

| Grupp | Färger per värde |
|---|---|
| Utvecklingsinriktning | rödorange (bebyggelse), grön (grön- och blåstruktur), gråblå (kommunikation), lila (annan) |
| Riksintressen (båda lagren) | grönt för natur, brunt för kultur, orange för friluftsliv, blått för kust och vatten, gråblått för fjäll, oliv för näringar, lila, grått och rött för anläggningar |
| Miljökvalitetsnormer | blågrön, marinblå, lila, grå, blå |
| Klimatrelaterade risker | blått för översvämning, rött för ras, orange för skred, brunt för erosion |
| Länsstyrelsens invändningar | rött, blågrönt, grönt, lila, gult |
| Mål, planer och program | marinblå (internationella), blå (nationella), lila (regionala), grön (kommunala) |
| Övriga grupper med ett värde | en egen färg |
| Plangeometri | svart |

**Att tänka på:** där ett genomskinligt överlägg ligger på en markanvändning blandas färgerna. Det är kanten som
visar vilket överlägg det är: strecktypen säger gruppen och färgen värdet. Inom en grupp med många värden, som de 23
riksintressena, är färgerna i samma tema ganska lika; använd identifieringsverktyget när du är osäker.

Punkten för *Länsstyrelsens invändningar* har en vit ring. Den syns tydligt på kartan men smälter in mot vit
bakgrund, till exempel i en teckenförklaring.
