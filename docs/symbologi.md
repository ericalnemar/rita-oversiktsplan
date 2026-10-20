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

Ett undantag: **pilspetsarna** i utvecklingsinriktningens linjeändar (se nedan). QGIS skriver dem i SLD med en egen
inställning som GeoServer inte förstår. Använd därför **Insticksprogram → Rita Översiktsplan → Spara stilar för
GeoServer (SLD)…**, som sparar en stilfil per innehållslager och gör om pilspetsarna till GeoServers sätt (en punkt i
linjens ände, vriden efter linjen, med funktionerna `endPoint` och `endAngle`). Lagren i GeoServer ska heta som
tabellerna, och geometrikolumnen heter `geom`.

Stilen för ett enskilt lager går också att spara som SLD i QGIS (lagrets egenskaper → Symbologi → Stil → Spara stil
→ SLD), men då utan omgjorda pilspetsar. De automatiska testerna kontrollerar att exporten bara innehåller
standardformer, vanliga filter och inga mönster, bilder eller typsnitt. Exporten är **inte provad i en riktig
GeoServer**.

## Idéer från andra kommuner

Utformningen bygger på en genomgång (oktober 2026) av fjorton kommuners digitala översiktsplaner (bland andra
Hudiksvall, Bromölla, Danderyd, Kävlinge, Kalix, Mullsjö, Uppsala, Vadstena och Västerås). Det som tagits med:

- utvecklingsinriktningen som ett **kraftigt schema för hela kommunen**: en färg per tema, breda halvgenomskinliga band,
  noder som ringar, storleken efter nivå och **pilspetsar** där stråken fortsätter;
- **namn i kartan**, som områdesbeteckningar i en tryckt översiktsplan;
- **detaljer först när man zoomat in** (punkter och linjer från 1:25 000);
- markanvändningen **täcker till 80 procent**, så att bakgrundskartan anas.

Flera kommuner visar också *förändring* med samma färg i olika styrka (befintligt ljust, nytt mörkare eller
skrafferat). Det bygger på fältet *användningsstatus*, som inte finns i ÖP-katalogen 2.2. Här är det
utvecklingsinriktningen ovanpå markanvändningen som visar förändringen.

## Gruppen avgör symbolen, värdet avgör färgen

Varje **grupp**, till exempel *Klimatrelaterade risker*, har en egen symbol: en egen kantlinje (strecktyp och
tjocklek), som också används när gruppen ritas som linje, och en egen punktform. Då ser man vilken grupp ett objekt
hör till. **Värdena inom gruppen** har samma symbol och skiljs åt med färgen, till exempel blått för översvämning och
rött för ras. Testerna kontrollerar att ingen grupp har samma kant eller samma punkt som en annan.

| Grupp | Kant och linje | Punkt |
|---|---|---|
| Mark- och vattenanvändning | färg som täcker till 80 %, ingen kant (i en etapp: kraftig streckad kant) | fylld cirkel |
| Plangeometri | kraftig streck-prick, ingen fyllning, inget namn | – |
| Område | tät prickad, ingen fyllning | – |
| Utvecklingsinriktning | mjuk kant; linjer som breda band med pilspets | ring kring en prick |
| Riksintresse, kommunens ställningstagande | heldragen | triangel |
| Riksintressen enligt 3 och 4 kap. MB (underlag) | tunn streckad | ihålig triangel |
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
punktform (triangel). Underlaget har tunn streckad kant och ihålig punkt, ställningstagandet heldragen kant. Båda har en mycket svag fyllning
(cirka 8 %), så att man ser var riksintresset gäller, och en bred halvgenomskinlig bård längs insidan av kanten, och namnet står längs kanten, som i många tryckta
översiktsplaner. Riksintressena är ofta stora och överlappar varandra: med den tidigare, starkare fyllningen blandades färgerna där de låg på
varandra och kartan blev grumlig, och namnet stod två gånger när både riksintresset och ställningstagandet syntes.
Nu syns markanvändningen inuti, varje gräns syns var för sig och namnet står en gång.

Bården blir smalare när man zoomar ut, i tre steg, så att den inte kladdar ihop längs flikiga kuster och sjöar:

| Skala | Bård | Kant |
|---|---|---|
| inzoomad, till 1:50 000 | 2,4 mm | 0,5 mm |
| kommunkartan, 1:50 000–1:150 000 | 1,2 mm | 0,4 mm |
| län och region, utzoomad förbi 1:150 000 | 0,6 mm | 0,3 mm |

Stegen är skalregler i stället för en fast referensskala, eftersom skalreglerna följer med till GeoServer (SLD) och en
referensskala inte gör det. Vill du se namnen på underlaget
(till exempel innan du skapat några ställningstaganden) slår du på etiketterna under lagrets egenskaper.

Mark- och vattenanvändningen är grunden och skiljs åt med färgen. Färgskillnaden mäts med CIEDE2000 (ΔE00), ett
standardmått på hur olika två färger ser ut för ögat, och testerna kontrollerar att alla par ligger på minst 8,5.

## Mark- och vattenanvändning

Grunden i kartan. Färgen täcker till 80 procent, så att bakgrundskartan anas, och befintlig användning har ingen kant. Där det finns ett
motsvarande markslag i Lantmäteriets **Topografi 10** har användningen markslagets färg ur Lantmäteriets stilfil för
QGIS, så att befintlig användning ser ut som Lantmäteriets karta (och som det verktyget *Markanvändning från
Topografi 10* skapar). Övriga värden utgår från Boverkets färger för detaljplanens användningsområden, med samma
färgkoder som i Rita Detaljplan; där de ligger för nära varandra har värdet fått en egen färg i samma färgfamilj.

**Utbyggnadsordning:** har planen etapper (Planens uppgifter, fliken Utbyggnadsordning) ritas mark- och
vattenanvändning i en etapp med kraftig streckad kant i en mörk ton, och färgen går från mättad och något mörkare
(första etappen) till ljus (sista etappen), i samma färgton. Ytor utan etapp ritas som ovan. (Att bara göra färgen
mörkare gjorde gult till oliv, som såg ut som en annan användning.) Etappen står under namnet i kartan.

| Innehållstyp | Färg | Ursprung |
|---|---|---|
| Bostadsbebyggelse | ljust gulbrun | Topografi 10: Låg bebyggelse |
| Funktionsblandad bebyggelse | brunorange | Topografi 10: Sluten bebyggelse |
| Service | röd | detaljplan S, D |
| Verksamheter | ljusgrå | Topografi 10: Industri- och handelsbebyggelse |
| Teknisk infrastruktur | gråblå | (detaljplanens E är blågrå men för nära W) |
| Energiproduktion | blåviolett | – |
| Vägtrafik | mellangrå; vägar som linje ljusgrå | (GATA:s ljusgrå låg för nära Topografi 10:s industrigrå) |
| Järnväg | mörkare grå | (detaljplanens T är grå men för nära GATA) |
| Luftfart | ljuslila | – |
| Sjöfart | marinblå | – |
| Vatten | ljusblå | Topografi 10: Sjö, hav och vattendrag |
| Fiske | klarblå | – |
| Vattenbruk | blågrön | – |
| Grönområde | ljust blågrön | nära Topografi 10:s idrottsplaner (som låg för nära skogen) |
| Natur- och kulturlandskap | nästan vit, gulaktig | Topografi 10: Öppen mark |
| Landsbygd | gråbeige | – |
| Friluftsliv och rekreation | grön | detaljplan N |
| Jordbruk | ljusgul | Topografi 10: Åker |
| Skogsbruk | ljusgrön | Topografi 10: Barr- och blandskog |
| Renskötsel | grågrön | – |
| Annan mark- och vattenanvändning | rosa | – |

De två som ligger närmast varandra är *Vägtrafik* och *Landsbygd* (ΔE00 9,0). Topografi 10:s ljusaste färger (öppen mark, industrigrå) syns svagt mot vit bakgrund, som i Lantmäteriets egen karta.

Valen är tolkningar. Till exempel kunde *Service* ha fått detaljplanens färg för C (centrum). Säg till om en annan
motsvarighet passar bättre.

Linjer i markanvändningen är streckade i en mörkare ton av färgen. Punkter är cirklar i färgen.

## Utvecklingsinriktning: ett schema för hela kommunen

Utvecklingsinriktningen är gjord för att läsas i hela kommunen, i skala 1:100 000–1:400 000, och syns i alla skalor.

- **Färgen visar temat**, alltså den kompletterande utvecklingsinriktningen: orange för bebyggelsestruktur, grön för
  grön- och blåstruktur, mörkgrå för kommunikation och lila för annan utvecklingsinriktning. Utan tema är den grå.
- **Storleken visar sambandsnivån**, i tre steg:

  | Sambandsnivå | Band (linje) | Nod (ring) | Ytans kant |
  |---|---|---|---|
  | Internationell, nationell eller regional | 5 mm | 12 mm | 1,6 mm |
  | Kommunal | 3,4 mm | 8,5 mm | 1,1 mm |
  | Lokal, eller ingen sambandsnivå | 2 mm | 6 mm | 0,7 mm |

- **Linjer** är breda, halvgenomskinliga band (ca 60 % täckning) med en **pilspets**. Bebyggelsestruktur,
  kommunikation och annan utvecklingsinriktning får en pil där man slutade rita: rita alltså stråk och
  utbyggnadsriktningar **från orten och utåt**. Grön- och blåstruktur (samband) får pilar i båda ändar. Det är
  standarden; i *Tilldela innehåll* kan du välja själv med kryssrutorna **Pilspets: där linjen slutar / där linjen
  börjar** (en, båda eller ingen). Valet sparas i pluginets eget fält `rita_pilar` (*slut*, *start*, *båda*, *ingen*;
  tomt = temats standard), som inte följer med i exporten till Lantmäteriet.
- **Punkter** (noder) är en ring kring en prick i temats färg.
- **Inzoomat** (från 1:50 000, till exempel i en tätort) blir band, pilar, ringar och kanter mindre, ungefär hälften,
  med ett minsta mått så att den lokala nivån syns: band 1,2 mm, pil 3 mm, ring 4 mm. Annars tar en pil på en kort
  linje över tätortskartan. Pilen är 1,8 gånger bandets bredd.
- **Ytor** har en svag fyllning (ca 35 %) och en **mjuk kant**: fyra linjer i temats färg ovanpå varandra, från
  bred och svag ytterst till smal och tydligare innerst, så att gränsen ser luddig ut (gränserna i en
  översiktsplan är illustrativa). Det är vanliga linjer med genomskinlighet, så det fungerar även i GeoServer.

## Namn och skalor

Innehållets **namn** visas i kartan med mörk text och vit kant. Utvecklingsinriktningens namn syns alltid, övrigas
från 1:100 000. Fyll i namnet i *Tilldela innehåll*, till exempel en områdesbeteckning som "B4".

**Punkter och linjer** (utom utvecklingsinriktningen) är detaljer och syns först från **1:25 000**, så att
kommunkartan inte blir grötig. Zooma in för att se och redigera dem. Ytor syns i alla skalor. Gränserna kan ändras
under lagrets egenskaper → Visning (*Skalberoende synlighet*).

## Övrigt innehåll (överlägg)

Övrigt innehåll ligger ovanpå markanvändningen. **Ytorna** ritas alla på samma sätt, som kommunens ställningstagande
till riksintressena:

- gruppens kant (strecktypen och tjockleken i tabellen ovan) i värdets färg,
- en bred halvgenomskinlig **bård på insidan av kanten**, som blir smalare när man zoomar ut (se skalstegen ovan),
- en **mycket svag fyllning** (cirka 8 %), så att man ser var innehållet gäller,
- **namnet längs kanten**, i bården.

Markanvändningen syns igenom, och innehåll får överlagra varandra enligt Boverket utan att kartan blir grumlig.
Undantagen är markanvändningen (heltäckande färg, egen stil), utvecklingsinriktningen (eget schema),
och plangeometrin och områden (bara en gräns; plangeometrin visar inget namn). För riksintressena, både underlaget och
kommunens ställningstagande, säger namnet också vilket riksintresse det är, till exempel *Vänern – Turism och rörligt
friluftsliv*. Finns både underlaget och ställningstagandet för samma riksintresse står namnet två gånger; släck då
det ena lagret. Några grupper har ihåliga punkter: underlaget och några grupper med ett enda
värde, för att de ska få en egen punktform.

| Grupp | Färger per värde |
|---|---|
| Riksintressen (båda lagren) | grönt för natur, brunt för kultur, orange för friluftsliv, blått för kust och vatten, gråblått för fjäll, oliv för näringar, lila, grått och rött för anläggningar |
| Miljökvalitetsnormer | blågrön, marinblå, lila, grå, blå |
| Klimatrelaterade risker | blått för översvämning, rött för ras, orange för skred, brunt för erosion |
| Länsstyrelsens invändningar | rött, blågrönt, grönt, lila, gult |
| Mål, planer och program | marinblå (internationella), blå (nationella), lila (regionala), grön (kommunala) |
| Övriga grupper med ett värde | en egen färg |
| Plangeometri | svart |

**Att tänka på:** där överlägg ligger på en markanvändning blandas färgerna något. Det är kanten och bården som
visar vilket överlägg det är: strecktypen säger gruppen och färgen värdet. Inom en grupp med många värden, som de 23
riksintressena, är färgerna i samma tema ganska lika; använd identifieringsverktyget när du är osäker.

Punkten för *Länsstyrelsens invändningar* har en vit ring. Den syns tydligt på kartan men smälter in mot vit
bakgrund, till exempel i en teckenförklaring.
