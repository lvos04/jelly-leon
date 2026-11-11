# ADR-0029 — B03-017: prototype met twee modules — één DLL, eigen Ed25519-controle, SQLite van de host

- **Status:** Aanvaard (2026-11-11). Uitvoering van ADR-0016; eerste gate van golf 1 (`B03_FASERING.md`).
- **Werkpakket:** B03-017; tests JLT-68, JLT-64, JLT-65.
- **Bewijs:** `plugins/JellyLeon/tests/` (xunit) en `tools/jelly-leon/e2e/` (stock 12.4 en de eigen image). Alles op de
  ontwikkelmachine; de echte NAS is **NIET GEVALIDEERD**.

## Context

ADR-0016 koos één plugin met een kern en modules en eiste als eerste gate een prototype met twee modules dat op de fork
én op de stock 12.x-image laadt en elke `/connector/v1`-route precies één keer registreert. Drie zaken waren nog open:

1. **Vorm van de assembly.** ADR-0016 punt 4 staat een tweede DLL toe. De image kopieert nu precies één bestand
   (`install_plugins()` in `deploy/allinone/entrypoint.sh`).
2. **Handtekeningcontrole.** De Hub tekent tokens met Ed25519 (contract 1.3 §4). .NET 10 heeft daarvoor geen publieke
   API en de 12.4-image levert geen cryptobibliotheek mee.
3. **Opslag.** Elke module krijgt een eigen SQLite (ADR-0016, ADR-0020). De 12.4-image levert
   `Microsoft.Data.Sqlite.dll` 10.0.x en de native SQLite-bibliotheek zelf mee.

## Besluit

1. **Eén DLL**: `Jellyfin.Plugin.JellyLeon.dll` bevat `Core/**` en `Modules/**`. Geen tweede assembly en geen
   meegeleverde pakketten: de pluginmap blijft één bestand, er kan geen versieverschil tussen kern en module ontstaan
   en de bestaande installatie in de image blijft ongewijzigd.
2. **Prototypemodules: Devices en Quality.** Devices luistert naar afspeelsessies (teller per methode en apparaat),
   Quality houdt bevindingen en scans bij en declareert het jobtype `quality.scan`. Samen raken ze elk gedeeld deel:
   connector, outbox, idempotentie, Hub-pin, geheimenmap, `UserDeleted`, privacyregister en de health-samenvoeging.
3. **Modules zijn gewone klassen achter `IJellyLeonModule`** (slug, itemtypen, eventtypen, jobtypen, register van
   persoonsgegevens, `Items`, `VerwijderGebruiker`, `TelGebruiker`, `ControleerOpslag`, `Exporteer`). `ModuleRegistry`
   weigert bij het starten een dubbele slug, een dubbel itemtype, eventtype of jobtype (no-go "gedeelde singleton die
   per module anders is"). Alle modules staan standaard **uit**.
4. **Eén routetabel** (`Core/Http/RouteTable.cs`) is de bron voor de controllers, de pipeline, het OpenAPI-document
   (`docs/openapi/jelly-leon-plugin.openapi.json`, gegenereerd en door een drifttest bewaakt) en de E2E-controle
   "elke route precies één keer". Controllers hebben geen `[ApiController]` en geen `[Authorize]`: de servereigen
   modelbinding en foutvorm zouden het contractformaat van §5 doorkruisen (ADR-0030).
5. **Ed25519 alleen controleren, in eigen C#** (`Core/Hub/Ed25519.cs`, RFC 8032 §5.1.7 met `BigInteger`). Er is geen
   geheim sleutelmateriaal in de plugin, dus geen constante-tijd-eis. Strikt: `S < L`, canonieke puntcodering, sleutel
   32 en handtekening 64 bytes. De tests ondertekenen met een onafhankelijke implementatie (BouncyCastle, alleen in het
   testproject) en bevatten de testvectoren van RFC 8032.
6. **SQLite van de host**: de plugin bouwt tegen `Microsoft.Data.Sqlite.Core` met `ExcludeAssets="runtime"` en levert
   niets mee. Elke database staat onder `/config/data/jelly-leon/<module>/`, heeft migraties via `user_version` en
   maakt vóór elke migratie een kopie `<db>.v<versie>.<tijdstempel>.bak` (hoogstens drie, hoogstens dertig dagen; de
   zojuist gemaakte kopie wordt nooit opgeruimd).
7. **Schrijfbereik**: de plugin schrijft uitsluitend onder `/config/data/jelly-leon/`, `/cache/jelly-leon/` en
   `/run/jelly-leon/` (`JlPaths.MagSchrijven`). Niets schrijft in de bibliotheek, de metadata, de kijkgeschiedenis of de
   gebruikersgegevens van de server (HARDE EIS; de analyzer van B03-017 bewaakt dit bij het bouwen).

## Alternatieven

- *Kern-DLL plus een DLL per module:* geeft niets wat de schakelaar per module niet al geeft, maar wel een tweede
  bestand in de image en een mogelijk versieverschil. Verworpen voor v1; ADR-0016 punt 4 blijft mogelijk.
- *BouncyCastle of NSec meeleveren:* een tweede bestand (3–6 MiB) of een native bibliotheek in de pluginmap en een
  extra afhankelijkheid om te volgen. Verworpen: alleen verificatie is nodig en dat is klein en volledig te testen.
- *Wachten op een Ed25519-API in .NET:* geen datum bekend. Verworpen. Komt die API er, dan vervangt ze
  `Ed25519.Verifieer` zonder verder iets te wijzigen.
- *Eigen SQLite-bundel meeleveren:* dubbele native bibliotheek naast die van de server. Verworpen.

## Gevolgen

- Een nieuwe forkbasis met een andere `Microsoft.Data.Sqlite`-hoofdversie vraagt een nieuwe build van de plugin; de
  smoketest op stock en fork vangt dit.
- Verificatie met `BigInteger` kost enkele milliseconden per token. Voor de Hub die elke 30–60 s pollt is dat ruim
  voldoende; een cache is niet nodig.
- Faalt het prototype alsnog op een latere 12.x, dan geldt de terugval van ADR-0016 punt 6.

## Verificatie

- xunit: registratie zonder dubbele namen, schakelaars, eigen database per module, RFC 8032-vectoren, migratiekopieën.
- JLT-68 (E2E): laden op stock 12.4 en op de eigen image; de routetabel van de draaiende server bevat elke
  `/connector/v1`-route precies één keer.
- JLT-64: met alle modules uit gedraagt de server zich als stock (alleen de eigen routes komen erbij).
