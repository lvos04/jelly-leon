# ADR-0037 — Segmentprovider en gerichte publicatie

B03-071 gebruikt de publieke plugin-ABI van Jellyfin 12.4 en de bestaande pluginassembly. De vaste providernaam is `Jelly Leon Segmenten`. Jellyfin gebruikt daarvoor de GUID-weergave van de MD5 van de naam in kleine letters en UTF-16LE.

De server geeft een segment terug zonder provider-ID. De publicatieadapter vraagt daarom aan de manager welke providers geregistreerd zijn. Hij maakt voor één leesopdracht nieuwe bibliotheekopties die alle andere providers uitsluiten. De manager selecteert de eigen rijen in de database vóór de omzetting naar DTO's. De adapter vergelijkt type en grenzen en verwijdert uitsluitend rij-ID's uit die selectie. Elke nieuwe rij krijgt een nieuwe ID en de vaste eigen provider-ID. Dit blijft werken als twee providers dezelfde tijdcodes publiceren. De analyzer staat de twee schrijvende managerleden uitsluitend toe in deze adapter.

De extractietaak leest de gewenste publicatie uit `segments.db`. De beheerlaag bewaart kandidaten, menselijke bevestigingen en gewenste publicaties in die eigen database. De module staat bij installatie uit. Een hoofdstuk met een herkenbare naam levert een kandidaat op tot het begin van het volgende hoofdstuk of het einde van het item.

De online back-up bevat ook vastgelegde WAL-pagina's. Vóór een migratie controleert de opslaglaag de bron en de kopie. Alle openstaande schemawijzigingen vormen één transactie. Bij een fout blijven de vorige schemaversie en de opgeslagen correcties beschikbaar.
