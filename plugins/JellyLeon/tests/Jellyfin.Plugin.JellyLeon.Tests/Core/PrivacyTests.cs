using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Xml.Serialization;
using Jellyfin.Data;
using Jellyfin.Data.Events.Users;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Database.Implementations.Enums;
using Jellyfin.Plugin.JellyLeon.Configuration;
using Jellyfin.Plugin.JellyLeon.Core.Http;
using Jellyfin.Plugin.JellyLeon.Core.Modules;
using Jellyfin.Plugin.JellyLeon.Core.Privacy;
using Jellyfin.Plugin.JellyLeon.Core.Storage;
using Jellyfin.Plugin.JellyLeon.Modules.Devices;
using Jellyfin.Plugin.JellyLeon.Modules.Quality;
using Jellyfin.Plugin.JellyLeon.Tests.Hulp;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Jellyfin.Plugin.JellyLeon.Tests.Core;

/// <summary>Eén IsKid, één UserDeleted-afhandeling voor alle modules, en geheimen die nergens meereizen.</summary>
public sealed partial class PrivacyTests : IDisposable
{
    private readonly Harnas _h = new();

    public void Dispose() => _h.Dispose();

    [Fact]
    public void IsKid_ElkSignaalApartIsGenoeg()
    {
        foreach (var grens in new[] { false, true })
        {
            foreach (var tags in new[] { 0, 2 })
            {
                foreach (var schemas in new[] { 0, 1 })
                {
                    var gebruiker = new User("profiel", "aanbieder", "aanbieder");
                    if (grens)
                    {
                        gebruiker.MaxParentalRatingScore = 0;
                    }

                    if (tags > 0)
                    {
                        gebruiker.SetPreference(PreferenceKind.BlockedTags, ["eng", "geweld"]);
                    }

                    if (schemas > 0)
                    {
                        gebruiker.AccessSchedules.Add(new AccessSchedule(DynamicDayOfWeek.Everyday, 8, 20, gebruiker.Id));
                    }

                    _h.Gebruikers.Setup(g => g.GetUserById(gebruiker.Id)).Returns(gebruiker);
                    foreach (var rolKind in new[] { false, true })
                    {
                        var verwacht = grens || tags > 0 || schemas > 0 || rolKind;
                        Assert.Equal(verwacht, _h.Dienst<KidPolicy>().IsKid(gebruiker, rolKind));
                    }
                }
            }
        }
    }

    [Fact]
    public void IsKid_LeestDeSignalenVanHetAccount()
    {
        bool IsKid(User account)
        {
            _h.Gebruikers.Setup(g => g.GetUserById(account.Id)).Returns(account);
            return _h.Dienst<KidPolicy>().IsKid(account);
        }

        Assert.False(IsKid(new User("volwassene", "aanbieder", "aanbieder")));

        var metGrens = new User("kind-a", "aanbieder", "aanbieder") { MaxParentalRatingScore = 10 };
        Assert.True(IsKid(metGrens));
        Assert.True(KidPolicy.Signalen(metGrens).HeeftLeeftijdsgrens);

        var metTags = new User("kind-b", "aanbieder", "aanbieder");
        metTags.SetPreference(PreferenceKind.BlockedTags, ["eng"]);
        Assert.True(IsKid(metTags));
        Assert.Equal(1, KidPolicy.Signalen(metTags).GeblokkeerdeTags);

        var metSchema = new User("kind-c", "aanbieder", "aanbieder");
        metSchema.AccessSchedules.Add(new AccessSchedule(DynamicDayOfWeek.Everyday, 8, 20, metSchema.Id));
        Assert.True(IsKid(metSchema));
        Assert.Equal(1, KidPolicy.Signalen(metSchema).Toegangsschemas);
    }

    [Fact]
    public async Task GebruikerVerwijderd_LaatInGeenEnkeleModuleIetsAchter()
    {
        var weg = new User("weg", "aanbieder", "aanbieder") { MaxParentalRatingScore = 10 };
        _h.Gebruikers.Setup(g => g.GetUserById(weg.Id)).Returns(weg);
        var kindbeleid = _h.Dienst<KidPolicy>();
        var voorstel = kindbeleid.VoorAccount(weg.Id);
        Assert.True(voorstel.IsKid);
        Assert.Equal(Kinderprofiel.Kind, kindbeleid.Bevestig(weg.Id, true, voorstel.Etag).Status);
        var blijft = Guid.Parse("99999999-8888-4777-8666-555555555555");
        var ander = new User("ander", "aanbieder", "aanbieder") { Id = blijft, MaxParentalRatingScore = 5 };
        _h.Gebruikers.Setup(g => g.GetUserById(blijft)).Returns(ander);
        Assert.True(kindbeleid.IsKid(ander));
        var item = Guid.Parse("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee");
        var nu = _h.Klok.Nu;

        // Devices staat aan, Quality staat uit: ook een uitgeschakelde module ruimt op.
        _h.Schakelaars.Zet("devices", true);
        _h.Schakelaars.Zet("quality", false);
        var devices = _h.Dienst<DevicesModule>();
        var quality = _h.Dienst<QualityModule>();
        devices.RegistreerStart([weg.Id, blijft], "TV Woonkamer", "sessie-1", "transcode", true, nu);
        devices.RegistreerStart([weg.Id], "Telefoon", "sessie-2", "direct_play", false, nu);
        quality.MeldBevinding(item, "audio_clipping", "waarschuwing", nu);
        quality.Onderdruk(item, "audio_clipping", weg.Id, nu);
        quality.Onderdruk(Guid.NewGuid(), "audio_clipping", blijft, nu);

        // Het account heeft ook een idempotency-rij in de kern (een instelling gewijzigd).
        _h.Sessies.Wie = new SessieIdentiteit(weg.Id, true, false);
        var etag = (await _h.Roep("devices.settings.get")).Kop["ETag"];
        var gewijzigd = await _h.Roep("devices.settings.put", "{\"bewaar_dagen\":14}", ["Idempotency-Key: " + Guid.NewGuid(), "If-Match: " + etag]);
        Assert.Equal(200, gewijzigd.Status);

        var privacy = _h.Dienst<PrivacyService>();
        Assert.Equal(5, privacy.TelGebruiker(weg.Id));
        Assert.Contains("kinderprofielen.db:kinderprofielen", Vindplaatsen(weg.Id));
        Assert.NotEmpty(Vindplaatsen(weg.Id));
        Assert.NotEmpty(RuweVindplaatsen(weg.Id));

        await new UserDeletedConsumer(() => privacy, NullLogger<UserDeletedConsumer>.Instance).OnEvent(new UserDeletedEventArgs(weg));

        Assert.Equal(0, privacy.TelGebruiker(weg.Id));
        Assert.Empty(Vindplaatsen(weg.Id));

        // Ook niet meer in de bestanden zelf (vrije pagina's, WAL): secure_delete en het inkorten van het WAL.
        Assert.Empty(RuweVindplaatsen(weg.Id));
        Assert.NotEmpty(RuweVindplaatsen(blijft));
        Assert.Equal(3, privacy.TelGebruiker(blijft));
        Assert.Equal(Kinderprofiel.Voorgesteld, kindbeleid.VoorAccount(blijft).Status);

        // Een tweede keer is onschadelijk.
        Assert.Equal(0, privacy.VerwijderGebruiker(weg.Id));
    }

    [Fact]
    public async Task PrivacyRegister_NoemtElkeTabelMetDoelEnBewaartermijn()
    {
        var antwoord = await _h.Roep("privacy.register");
        Assert.Equal(200, antwoord.Status);
        Assert.Empty(SchemaControle.Afwijkingen(OpenApiBouwer.Bouw(), "PrivacyRegister", antwoord.Json));
        var regels = antwoord.Json!["items"]!.AsArray();
        Assert.Contains(regels, r => (string?)r?["tabel"] == "kinderprofielen" && (string?)r?["module"] == "core");
        foreach (var module in _h.Dienst<ModuleRegistry>().Alle)
        {
            Assert.Contains(regels, r => r!["module"]!.GetValue<string>() == module.Slug);
        }

        Assert.All(regels, r =>
        {
            Assert.False(string.IsNullOrWhiteSpace(r!["doel"]!.GetValue<string>()));
            Assert.False(string.IsNullOrWhiteSpace(r["bewaartermijn"]!.GetValue<string>()));
            Assert.False(string.IsNullOrWhiteSpace(r["bij_verwijderen"]!.GetValue<string>()));
        });

        var geregistreerd = regels.Select(r => (r!["module"]!.GetValue<string>(), r["tabel"]!.GetValue<string>())).ToHashSet();
        var kern = _h.Dienst<CoreDatabase>();
        kern.Db.Met(v => JlDatabase.Getal(v, "SELECT 1"));
        kern.Kinderprofielen.Met(v => JlDatabase.Getal(v, "SELECT 1"));
        foreach (var module in _h.Dienst<ModuleRegistry>().Alle)
        {
            module.ControleerOpslag();
        }

        // Nieuwe tabellen vereisen een beoordeling, ook als het account in JSON of een samengestelde sleutel staat.
        (string, string)[] zonderAccount = [
            ("core", "jobs"),
            ("devices", "instellingen"),
            ("quality", "instellingen"), ("quality", "findings"), ("quality", "scans"),
            ("segments", "instellingen"), ("segments", "items"), ("segments", "scope"), ("segments", "beheer"),
            ("segments", "exports"), ("segments", "weesmoment")];
        var data = _h.Dienst<JlPaths>().DataRoot;
        foreach (var bestand in Directory.GetFiles(data, "*.db", SearchOption.AllDirectories))
        {
            var module = Directory.GetParent(bestand)!.Name;
            using var v = OpenTestDb(bestand, SqliteOpenMode.ReadOnly);
            foreach (var rij in JlDatabase.Rijen(v, "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT GLOB 'sqlite_*'"))
            {
                var tabel = (string)rij[0]!;
                var kolommen = JlDatabase.Rijen(v, "SELECT lower(replace(name, '_', '')) FROM pragma_table_info($t)", ("$t", tabel));
                var accountkolom = kolommen.Any(k => (string)k[0]! is "userid" or "accountid" or "gebruikerid" or "gebruiker" or "account" or "actor" or "owner");
                if (accountkolom || !zonderAccount.Contains((module, tabel)))
                {
                    Assert.Contains((module, tabel), geregistreerd);
                }
            }
        }
    }

    [Fact]
    public async Task Geheimen_StaanNietInInstellingenExportOfAntwoord()
    {
        _h.Koppel();
        _h.Schakelaars.Zet("devices", true);
        _h.Schakelaars.Zet("quality", true);
        var gebruiker = Guid.Parse("12121212-3434-4565-8787-909090909090");
        _h.Dienst<DevicesModule>().RegistreerStart([gebruiker], "TV Woonkamer", "sessie-1", "transcode", true, _h.Klok.Nu);
        _h.Dienst<QualityModule>().Onderdruk(Guid.NewGuid(), "audio_clipping", gebruiker, _h.Klok.Nu);

        var sleutelset = _h.Hub.Keyset();
        var sleutel = sleutelset["jwks"]!["keys"]![0]!["x"]!.GetValue<string>();
        var beleidsleutel = sleutelset["policy_public_key"]!["x"]!.GetValue<string>();
        var token = _h.Hub.Token(_h.Klok.Nu);
        var connector = await _h.RoepHub("connector.discover", token);
        Assert.Equal(200, connector.Status);
        var zout = Convert.ToHexStringLower(await File.ReadAllBytesAsync(Path.Combine(_h.Map, "data", "jelly-leon", "secrets", "opaque-id.salt"), TestContext.Current.CancellationToken));

        // De instellingen van de plugin (XML van de server) hebben geen veld voor een geheim.
        var velden = Velden(typeof(PluginConfiguration), []).ToList();
        Assert.NotEmpty(velden);
        Assert.DoesNotContain(velden, v => new[] { "key", "secret", "token", "password", "sleutel", "geheim", "wachtwoord", "pin", "jwks" }.Any(w => v.Contains(w, StringComparison.OrdinalIgnoreCase)));

        // Export per module en de beheerantwoorden bevatten geen sleutel, zout of account-ID.
        var teksten = _h.Dienst<ModuleRegistry>().Alle.Select(m => m.Exporteer().ToJsonString()).ToList();
        using var xml = new StringWriter(CultureInfo.InvariantCulture);
        new XmlSerializer(typeof(PluginConfiguration)).Serialize(xml, new PluginConfiguration());
        teksten.Add(xml.ToString());
        teksten.Add(connector.Json!.ToJsonString());
        teksten.Add((await _h.Roep("hublink.get")).Json!.ToJsonString());
        teksten.Add((await _h.Roep("modules.list")).Json!.ToJsonString());
        teksten.Add((await _h.Roep("devices.status")).Json!.ToJsonString());
        teksten.Add((await _h.Roep("quality.status")).Json!.ToJsonString());
        foreach (var tekst in teksten)
        {
            Assert.DoesNotContain(sleutel, tekst, StringComparison.Ordinal);
            Assert.DoesNotContain(beleidsleutel, tekst, StringComparison.Ordinal);
            Assert.DoesNotContain(token, tekst, StringComparison.Ordinal);
            Assert.DoesNotContain(zout, tekst, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(gebruiker.ToString("N"), tekst, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain(gebruiker.ToString("D"), tekst, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("TV Woonkamer", tekst, StringComparison.Ordinal);
        }

        // Controleer de volledige beheerexports terwijl de pin actief is, ook op de policy-sleutel.
        foreach (var slug in new[] { "devices", "quality" })
        {
            var export = await _h.Roep(slug + ".export");
            Assert.Equal(200, export.Status);
            var inhoud = export.Json!.ToJsonString();
            Assert.DoesNotContain(sleutel, inhoud, StringComparison.Ordinal);
            Assert.DoesNotContain(beleidsleutel, inhoud, StringComparison.Ordinal);
            Assert.DoesNotContain(token, inhoud, StringComparison.Ordinal);
        }

        // De pin zelf staat alleen in de geheimenmap.
        var metPin = Directory.GetFiles(_h.Map, "*", SearchOption.AllDirectories)
            .Where(b => !b.EndsWith(".db", StringComparison.Ordinal) && !b.Contains(".db-", StringComparison.Ordinal))
            .Where(b => File.ReadAllText(b).Contains(sleutel, StringComparison.Ordinal))
            .ToList();
        Assert.Equal([Path.Combine(_h.Map, "data", "jelly-leon", "secrets", "hub-pin.json")], metPin);
    }

    private static IEnumerable<string> Velden(Type type, HashSet<Type> gezien)
    {
        if (!gezien.Add(type))
        {
            yield break;
        }

        foreach (var eigenschap in type.GetProperties())
        {
            yield return eigenschap.Name;
            if (eigenschap.PropertyType.Assembly == typeof(PluginConfiguration).Assembly)
            {
                foreach (var diep in Velden(eigenschap.PropertyType, gezien))
                {
                    yield return diep;
                }
            }
        }
    }

    private static SqliteConnection OpenTestDb(string pad, SqliteOpenMode modus = SqliteOpenMode.ReadWriteCreate)
    {
        var verbinding = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = pad, Mode = modus, Pooling = false }.ToString());
        verbinding.Open();
        return verbinding;
    }

    /// <summary>Doorzoekt plugindata en -cache als bytes, met inbegrip van SQLite-zijbestanden.</summary>
    private List<string> RuweVindplaatsen(Guid gebruiker)
    {
        var vormen = new[] { gebruiker.ToString("N"), gebruiker.ToString("D") };
        var naalden = vormen.Concat(vormen.Select(s => s.ToUpperInvariant()))
            .Append(_h.Dienst<PrivacyService>().Pseudoniem(gebruiker))
            .Append(_h.Dienst<DevicesModule>().Gegevensbeheer.ExportGebruiker(vormen[0]))
            .Append(_h.Dienst<QualityModule>().Gegevensbeheer.ExportGebruiker(vormen[0]))
            .Select(Encoding.ASCII.GetBytes)
            .Append(gebruiker.ToByteArray()).Append(gebruiker.ToByteArray(bigEndian: true))
            .ToList();
        var paden = _h.Dienst<JlPaths>();
        var mappen = new[] { paden.DataRoot, paden.CacheRoot }.Where(Directory.Exists);
        var gevonden = new List<string>();
        foreach (var bestand in mappen.SelectMany(map => Directory.GetFiles(map, "*", SearchOption.AllDirectories)))
        {
            byte[] inhoud;
            using (var stroom = new FileStream(bestand, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            {
                inhoud = new byte[stroom.Length];
                stroom.ReadExactly(inhoud);
            }

            if (naalden.Any(naald => inhoud.AsSpan().IndexOf(naald) >= 0))
            {
                gevonden.Add(Path.GetFileName(bestand));
            }
        }

        return gevonden;
    }

    private List<string> Vindplaatsen(Guid gebruiker)
    {
        var naalden = new[] { gebruiker.ToString("N"), gebruiker.ToString("D"), _h.Dienst<PrivacyService>().Pseudoniem(gebruiker) };
        var gevonden = new List<string>();
        foreach (var bestand in Directory.GetFiles(Path.Combine(_h.Map, "data", "jelly-leon"), "*.db", SearchOption.AllDirectories))
        {
            using var verbinding = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = bestand, Pooling = false }.ToString());
            verbinding.Open();
            var tabellen = new List<string>();
            using (var opdracht = verbinding.CreateCommand())
            {
                opdracht.CommandText = "SELECT name FROM sqlite_master WHERE type = 'table'";
                using var lezer = opdracht.ExecuteReader();
                while (lezer.Read())
                {
                    tabellen.Add(lezer.GetString(0));
                }
            }

            foreach (var tabel in tabellen)
            {
                using var opdracht = verbinding.CreateCommand();
#pragma warning disable CA2100 // Tabelnamen komen uit sqlite_master van de eigen testdatabase.
                opdracht.CommandText = "SELECT * FROM \"" + tabel + "\"";
#pragma warning restore CA2100
                using var lezer = opdracht.ExecuteReader();
                while (lezer.Read())
                {
                    for (var i = 0; i < lezer.FieldCount; i++)
                    {
                        var waarde = lezer.IsDBNull(i) ? string.Empty : Convert.ToString(lezer.GetValue(i), System.Globalization.CultureInfo.InvariantCulture)!;
                        if (naalden.Any(n => waarde.Contains(n, StringComparison.OrdinalIgnoreCase)))
                        {
                            gevonden.Add(Path.GetFileName(bestand) + ":" + tabel);
                        }
                    }
                }
            }
        }

        return gevonden;
    }
}
