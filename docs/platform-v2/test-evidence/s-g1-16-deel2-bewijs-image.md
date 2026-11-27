# S-G1-16 deel 2 — bewijs en bewaarde lokale image

Status: **Bezig**; **Sim-getest**; **NIET GEVALIDEERD (echte NAS)**; **NIET GEVALIDEERD (echte Hub)**.

## Herkomst

- Broncommit van de image: `48293b48ac48644e0d4433cf3193a96fbf35eac4`.
- Bewaarde tag: `jelly-leon:lokaal-48293b48a`.
- Gemeten image-ID: `sha256:09c2bb379cf09e0895a794dcf4979b3171d015d942dda67a67ad42231f43741b`.
- Grootte volgens Docker: 865208951 bytes.
- Webbron: `5ced8a24601e30038cafae5dab2f0520b3325427` (schone export van de vastgezette commit).
- Het OCI-revisionlabel en SOURCE_REVISIONS wijzen naar de broncommit. De bewijscommit erna wijzigt uitsluitend dit document en de rij B03-017 in EVIDENCE.json en EXCEL_TAKEN.json; code, tests en imagebronnen blijven gelijk. De tag wordt niet hernoemd naar de bewijscommit.

## Zelf uitgevoerde proeven

| Onderdeel | Uitkomst |
|---|---|
| plugins-bouw | exitcode 0; Time Elapsed 00:00:13.11 |
| plugins-test | exitcode 0; Passed!  - Failed:     0, Passed:   359, Skipped:     0, Total:   359, Duration: 7 s - Jellyfin.Plugin.JellyLeon.Tests.dll (net10.0) |
| analyzer-beoordeling | exitcode 0; analyzer_proef: in orde — 323 verboden aanroepen geven elk precies de verwachte bouwfout; de build faalt alleen daardoor |
| tools-zonder-shell | exitcode 0; 319 passed in 21.09s |
| shelltests-container | exitcode 0; 105 passed in 3.10s |
| consistentie | exitcode 0; Forkconsistentie in orde: basis v12.4 (83d0d0e7f76e), forkversie 12.4.0-jl.0. |
| register | exitcode 0; Patchregister in orde. |
| upstream-register | exitcode 0; Upstream-gedrag (serverdeel) in orde: 12 ankers gevonden, 6 runtime-tests gekoppeld, alle UG-verwijzingen bekend. |
| contract | exitcode 0; Contractkopieën in orde (online tegen GitHub): 2 bestanden byte-gelijk aan lvos04/ai-server-manager@e88a290c9; historie ongewijzigd: CONTRACT_1.2_CONFORMITEIT.md. |
| ruff | exitcode 0; All checks passed! |
| shellcheck | exitcode 0; (geen uitvoer) |
| actionlint | exitcode 0; (geen uitvoer) |
| server-restore | exitcode 0; Restored /src/src/Jellyfin.Database/Jellyfin.Database.Providers.Sqlite/Jellyfin.Database.Providers.Sqlite.csproj (in 2.32 sec). |
| server-bouw | exitcode 0; Time Elapsed 00:00:55.84 |
| image-bouw | exitcode 0; #33 DONE 11.3s |
| image-tag | exitcode 0; (geen uitvoer) |
| levenscyclus-022 | exitcode 0; RESULTAAT: GESLAAGD (59/59) |
| image-guard | exitcode 0; in orde: geen beperkt gelicentieerde testdata in image jelly-leon:lokaal-48293b48a |
| terugzet | exitcode 0; RESULTAAT: GESLAAGD (10/10) |
| upgrade | exitcode 0; RESULTAAT: GESLAAGD (18/18). Bij JLT-61(b) gaf stock 10.11.11 op de gemigreerde datamap HTTP 500. De proef herkende daarin geen expliciete downgradeweigering. |
| compat-api | exitcode 0; RESULTAAT: GESLAAGD (5/5) |
| upstream-runtime | exitcode 0; RESULTAAT: GESLAAGD (6/6) |
| pluginproef | exitcode 0; RESULTAAT: GESLAAGD {'JLT-64': {'geslaagd': 17, 'totaal': 17}, 'JLT-65': {'geslaagd': 17, 'totaal': 17}, 'JLT-68': {'geslaagd': 83, 'totaal': 83}} |
| startupfilter | exitcode 0; RESULTAAT: GESLAAGD (21/21 uitspraken) |

De pluginsuite telt 359 tests zonder skips. De forktoolsuite telt 424 tests zonder skips: 105 shelltests in een gepinde Python-container en 319 overige tests op de host. De negatieve analyzerbouw faalt met 323 fouten; de beoordelaar bevestigt precies de verwachte fouten, zonder andere bouwfout. Er is geen code of test veranderd.

## Omgevingsafwijkingen en bewijsgrens

- Eerste host-run forktools: 43 fouten, 366 groen, 15 skips. De zandbak toont systeemouder /home als eigenaar 65534 en heeft al no_new_privs. De 105 shelltests zijn daarom zonder wijziging of versoepeling opnieuw gedraaid in de gepinde testcontainer (de werkwijze van deel 1d); de overige 319 tests op de host.
- Upstream-solution: restore en build groen, 0 waarschuwingen en 0 fouten. De lokale suite telt 4059 groen, 131 fouten door ontbrekende libfontconfig.so.1 in de SDK-container en 16 bestaande upstream-skips (één Apple-test, twaalf Windows-gevallen, drie overgeslagen integratietests). Daardoor is lokaal ook geen OpenAPI-uitvoer gemaakt. Volgens POORTEN.md, P-jelly-leon, Valkuilen, is de CI-job server het bewijs voor de volledige suite en OpenAPI-controle. De uitkomst op de nieuwe bewijscommit wordt in het externe eindrapport vastgelegd; lokaal rood is geen lokale groene test.
- Eerste Buildx-aanroep stopte vóór het bouwen op een alleen-lezen activiteitsmap. BUILDX_CONFIG is naar de eigen ketenmap verplaatst; de herhaalde bouw is groen.
- Eerste levenscyclusproef: 58/59. De lokale umask 0002 maakte de proefmediamap 0775; de start weigerde terecht, maar eerder dan de verwachte padmelding. Herhaald met umask 0022 zoals CI: zie tabel. Geen productiecode of test veranderd.
- De lokale webkloon staat op een andere HEAD. Zij is niet gewijzigd; de image gebruikt een schone git archive-export van de vastgezette webcommit. De CI controleert de checkout van die commit afzonderlijk.
- Ruwe logs, proefrapporten en commandoregister blijven buiten de repo in de ketenmap S-G1-16/deel2. Zij zijn geen NAS-bewijs. De onafhankelijke review volgt na deze bouwstap.

## Wat nog open is

NIET GEVALIDEERD (echte NAS): de plugin draait nog op geen echte NAS; gebruiker moet de NAS-metingen uitvoeren. NIET GEVALIDEERD (echte Hub): de koppeling is alleen tegen de Hub-simulator getest. Besluit B1 bij de gebruiker: de serverroute voor pluginconfiguratie en een harde koppeling op de database; tevens de lege gedeelde tmpfs als /cache en het opvolgen van Verplicht 3. Geen absolute garantie afgeleid uit de groene simulatieproeven.

Gebouwd: één pluginassembly met Core en de prototypes Devices en Quality, analyzer, opslag- en startgrens, web-configgenerator. De IStartupFilter-spike is lokaal beproefd; volledige acceptatie en doorvoering blijven vervolgwerk. Nog open: export/import per module met preview_hash, de webhaakmodule en de modules WatchTogether, Recommendations, Subtitles en Segments. JLT-64/65/68 en volledige acceptatiemeting worden in S-G1-10 geboekt; Hub-koppeling in S-G1-12, webhaakmodule in S-G1-60, foutcatalogus/idempotentie in S-G1-14, privacy in S-G1-18, mountstatus in S-G1-20 en MediaGuard-vervoer in S-G1-50. Restgrenzen van deel 1 blijven gelden (ADR-0032): vooraf gelegde harde databasekoppeling en wissel door dezelfde UID tussen controle en openen; serverroute voor pluginconfiguratie; lege gedeelde tmpfs. De tmpfs-proef van deel 1h begon met eigenaar 568 op /config. Bij een eerste start als root met een andere eigenaar kan de eigenaarswissel al zijn uitgevoerd voordat de app de tmpfs afkeurt. Op de NAS nog meten: leegte van /dev/shm bij start; modus, eigenaar en grootte van tmpfs-/cache; preset Apps, NFSv4-ACL’s en fs.protected_hardlinks. Deze stap wijzigt deel 1 niet.

## Boeking en CI

Alleen B03-017 is toegevoegd aan EVIDENCE.json. In EXCEL_TAKEN.json blijft de bestaande taakdefinitie met hoofdletterveld ID behouden; aan diezelfde taak zijn de acht identieke bewijsvelden toegevoegd, zonder tweede taak of duplicaat-ID. Er is geen Excel-samenvoegcommando uitgevoerd.

Historische controle: volledige commit cc3e82b4dd5c9b210ce8cd98b69d19a52ae23213, Jelly Leon CI 42989190339: alle acht jobs completed/success. Er is geen historische rode job aangetroffen. De nieuwe CI-run, de twee uitgevoerde pluginproefstappen en git diff --stat tussen imagebron en bewijscommit worden in RAPPORT-A-BOUW-2b.md vastgelegd.
