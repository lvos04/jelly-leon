namespace Jellyfin.Plugin.JellyLeon.Core.Storage;

/// <summary>De database van Core: herhaalcache, idempotentie, outbox en de jobwachtrij van de planner.</summary>
internal sealed class CoreDatabase
{
    private static readonly string[] _migraties =
    [
        """
        CREATE TABLE hub_jti(iss TEXT NOT NULL, jti TEXT NOT NULL, exp INTEGER NOT NULL, methode TEXT NOT NULL,
            pad TEXT NOT NULL, idem TEXT, PRIMARY KEY(iss, jti));
        CREATE TABLE idempotentie(scope TEXT NOT NULL, sleutel TEXT NOT NULL, verzoek_hash TEXT NOT NULL,
            staat TEXT NOT NULL, status INTEGER, body TEXT, etag TEXT, gemaakt INTEGER NOT NULL, PRIMARY KEY(scope, sleutel));
        CREATE TABLE outbox(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, module TEXT NOT NULL,
            json TEXT NOT NULL, gemaakt INTEGER NOT NULL);
        CREATE TABLE jobs(id INTEGER PRIMARY KEY AUTOINCREMENT, soort TEXT NOT NULL, module TEXT NOT NULL,
            payload TEXT NOT NULL, staat TEXT NOT NULL, gemaakt INTEGER NOT NULL, gestart INTEGER, klaar INTEGER,
            uitkomst TEXT);
        CREATE INDEX jobs_staat ON jobs(staat, id);
        """,
    ];

    public CoreDatabase(JlPaths paden)
    {
        Db = new JlDatabase(paden.CoreDb, _migraties);
    }

    public JlDatabase Db { get; }
}
