"""Skapa bokmärken i planhandling: ett eget litet program (fönster) i Rita Översiktsplan som kopplar översiktsplanens textavsnitt
(Word) till planens innehåll med bokmärken, enligt Boverkets instruktion för texthantering i ÖP-modellen.

Byggt efter *Tagga planbeskrivning* i Rita Detaljplan (``rita_detaljplan/planbeskrivning/pbapp``): samma steg i
toppfältet, samma tema och samma byggstenar. Skillnaden är resultatet: i stället för en Word-fil med XML-del blir det
en kopia av Word-filen med bokmärken, och rader i planens tabeller ``dokumentavsnitt`` och ``avsnittsbokmärke`` som
kopplar varje bokmärke till planens objekt.

``session`` är programmets tillstånd utan Qt, ``host`` kopplingen till planen i QGIS, ``main`` fönstret och ``pages``
de fyra stegen."""
APP_NAME = "Skapa bokmärken i planhandling"
SETTINGS_NAME = "Rita Översiktsplan/Skapa bokmärken i planhandling"
