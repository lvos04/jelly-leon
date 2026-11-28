# Analysewerker

De plugin kan de werker starten met `/opt/jelly-leon/python/bin/python3 -IB -m jl_werker` als gebruiker en groep 568. S-G1-30 levert het proces met standaardinvoer en standaarduitvoer. S-G1-32 verzorgt de koppeling aan de plugin, de socket en de herstartbewaking. De overname-assistent van S-P40-82 gebruikt dezelfde interpreter.

Elke UTF-8-regel bevat één JSON-object van maximaal 1 MiB, exclusief de regeleinde. De werker houdt de verbinding open tot het einde van de invoer.

| Verzoek | Antwoord |
| --- | --- |
| `{"taak":"ping"}` | `{"antwoord":"pong"}` |
| `{"taak":"versies"}` | `versies` met de gemeten versies van Python, ffmpeg, ffprobe en ffsubsync |
| Ongeldige regel, extra veld of onbekende taak | `{"fout":"ongeldig_verzoek"}` |
| Bericht groter dan 1 MiB | `{"fout":"bericht_te_groot"}` |
| Gereedschap ontbreekt, stopt met een fout of antwoordt te laat | `{"fout":"gereedschap_onbeschikbaar"}` |

De opdrachtbouwer gebruikt vaste programma's en argumentlijsten. De vorm voor ffsubsync kiest WebRTC, één expliciete ondertitelinvoer en standaarduitvoer. De twee ffmpeg-vormen leveren null-uitvoer of ruwe audio op stdout. Geen van deze vormen opent een uitvoerbestand. De JSON-interface biedt uitsluitend de twee taken uit de tabel.

`requirements.lock` bevat de distributiehashes voor CPython 3.12 op Linux x86-64. Alleen srt vereist een bouwstap. De daarvoor gebruikte backend staat in `bouw.lock`. Bij een pakketupdate horen het geselecteerde artefact, de licentie in `licenties.json`, de leveranciersvermeldingen en de audit opnieuw te worden gecontroleerd. De meegeleverde licentieteksten staan bij de distributies in `site-packages`.

De offline rookproef start de werker, stuurt drie berichten, vergelijkt vier daadwerkelijk uitgevoerde versieopdrachten met de SBOM en controleert de rechten van de runtime. De proef oefent ook WebRTC op stilte, SQLite in geheugen en de TLS-context van de gedeelde interpreter. Voer de unittests vanuit deze map uit met `python -m pytest -q tests`.
