# S-G1-16, deel 1 — grensonderzoek

Status: **Bezig; NIET KLAAR**. Dit onderzoek is geen volledige veiligheidsvalidatie van B03-017.
Bronbasis: `0783c1987b38aaca8ade5cd0a1e8dd7f2bd0384b`.

## Open generieke optieregistratie

De nieuwe test `BrowserEnHostOptiesTests.HostOpties_OpenInfrastructuurEnGeneriekeImplementatieZijnJL0001`
faalde vóór het herstel: alle twaalf verwachte regels ontbraken. Na het herstel worden de twaalf vormen in
`Modules.Proef`, `Core.Http` en `Core.Storage` geweigerd. Gesloten opties voor een eigen type blijven toegestaan.
De negatieve proefassembly bevat ook de open fabriek en de open optiediensten.

`HostOptiesDraaienTests.OpenFabriek_IsJL0001_EnZetZonderAnalyzerDeHostinstellingTerug` compileert dezelfde bron
met en zonder analyzer. Zonder analyzer vervangt `Alles<T> : IOptionsFactory<T>` de ingestelde hostoptie:
`JsonOptions.JsonSerializerOptions.WriteIndented` gaat van `true` naar `false`. Hiervoor gebruikt de
proefcode geen reflectie of dynamic; alleen het testharnas laadt de gecompileerde proef. Het herstel sluit
hiermee een gat in de bestaande hostoptiecategorie. Geen nieuwe uitzondering of pakket toegevoegd.

## Padgrens: vier aangetoonde fouten, nog geen herstel

De zelfstandige proef staat buiten de repo onder `<WERKMAP>/.lokaal/ketens/S-G1-16/bouw1/padproef/`.
De uitvoer staat in `bouw1/padgrenzen.log` en het commandoregister in `bouw1/commando-resultaten.jsonl`
van dezelfde ketenmap. De projectmap bevat kopieën van `JlPaths`, `InternalWriteScope` en `JlDatabase`
uit de bronbasis. Alleen de twee controle/openvensters kregen een eenmalige proefhaak:
`GrensHaak.NaBestandsControle` vóór `FileStream` en `GrensHaak.NaDatabaseControle` vóór `SqliteConnection`.
De productiebestanden kregen deze haken niet. De foutvertaling is in de proef een eenvoudige IOException;
dat verandert geen padcontrole of schrijfhandeling.

| Proef | Opzet | Waarneming |
|---|---|---|
| Harde koppeling, tijdelijk bestand | `<doel>.tmp` is dezelfde inode als een synthetische buiten-database; `SchrijfAtomisch` schrijft | Buitenbestand wijzigt; geen weigering |
| Harde koppeling, database | Eigen databasenaam is dezelfde inode als een synthetische buiten-database; migratie verwijdert de proefrij | Buitenbestand wijzigt; geen weigering |
| Padwissel, bestand | Na de controles wordt de eigen bovenliggende map vervangen door een symbolische koppeling naar de proef-servermap | Buitenbestand wijzigt; geen weigering |
| Padwissel, database | Na de laatste controle wordt het databasepad een symbolische koppeling naar de proef-buiten-database | Buitenbestand wijzigt; geen weigering |

De buiten-database wordt per proef vers aangemaakt en bevat een niet-lege synthetische UserData-tabel.
De bytevergelijking vóór/na is in alle vier gevallen ongelijk. Exitcode 0 van het onderzoeksprogramma
betekent alleen dat het onderzoek is uitgevoerd; de opslaggrens is daarmee **niet groen**.
De proef gebruikt native `link` uitsluitend om testgegevens buiten de productierepo klaar te zetten.
Er is geen native uitzondering in de plugin of analyzer toegevoegd.

Reproductie, vanuit de repo en met de oorspronkelijke proefmap beschikbaar:

```sh
JL_ENV='-v <WERKMAP>/.lokaal/ketens/S-G1-16/bouw1/padproef:/proef' \
  flock <WERKMAP>/.lokaal/docker-build.lock nice -n 10 \
  <WERKMAP>/.lokaal/jl-dotnet.sh run --project /proef/Padproef.csproj -c Release -m:4
```

## Stop en vervolg

Het analyzerherstel is afzonderlijk afrondbaar. De opslaggrens vraagt een eigen herstelbereik met
een ontwerp dat controle en bestandsidentiteit aan elkaar bindt, inclusief SQLite-hoofdbestand,
WAL/SHM/journal, migratiekopieën, tijdelijke bestanden, mapaanmaak en verwijderen. Alleen opnieuw
controleren of `CreateNew` toepassen op het tijdelijke bestand sluit het hele gat niet.
De bestaande analyzer verbiedt native omwegen ook in `Core.Storage`; dat verbod wordt niet verruimd.
Een passende oplossing zonder nieuwe veiligheidsuitzondering is nog niet gebouwd of bewezen.

Daarom blijft deel 1 NIET KLAAR. Overige ADR-0032-grenzen zijn na deze stop niet opnieuw met
runtimeproeven onderzocht: BCL-mutaties op servercollecties, neveneffecten van toegestane leesleden,
impliciete aanroepen en BCL-interfaceaanroepen, nieuwe pakketten en tweede assemblies. De bestaande
analyzertests, opslagtests en namespacewacht blijven bestaan. Dit document accepteert geen restrisico.
Nieuwe, latente categorieën die de plugin niet gebruikt blijven vervolgpunt voor S-G1-12.
Kindprocesgedrag hoort bij B03-018; de huidige `GeenWerker` start geen proces.

B03-017 in EVIDENCE, lokale imagebouw en lokale imageproeven horen bij deel 2 na de reviews.
JLT-64/65/68 horen bij S-G1-10. Er zijn geen echte NAS, Emby, Hub, MediaGuard of accounts benaderd.
